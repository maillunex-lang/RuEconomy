"""Persistent 7-real-day calendar, bounded AI economy and world snapshots."""
from __future__ import annotations
import csv,json,time
from pathlib import Path
from .market import Market,CITIES
from .ai import AIManager
from .beta_features import BetaFeatures,GAME_DAY_SECONDS

class WorldEngine:
    def __init__(self,e: Market,features: BetaFeatures,seed=42):
        self.e=e
        self.features=features
        self.ai=AIManager(e,seed)
        self.prices={sku:(18 if sku.startswith("AGRI") else 12) for sku in e.goods}
        costs=Path(__file__).resolve().parents[1]/"docs/ECONOMY-BALANCING-1.1-COSTS-baseline.csv"
        with costs.open(encoding="utf-8",newline="") as f:
            for r in csv.DictReader(f):
                if e.goods[r["goods_id"]]["source_mode"]=="manufacturing":
                    sku=r["goods_id"];v=int(r["unit_cost_kopecks"])
                    self.prices[sku]=min(self.prices.get(sku,v),v) if self.prices.get(sku,12)>12 else v

    def bootstrap(self,enable=True):
        """Initial issuance explicitly booked in companies; never run more than once."""
        with self.e.atomic():
            for n,city in enumerate(CITIES):
                for name,cash,kind in (
                    ("household:"+city,20_000_000,"households"),
                    ("market-maker-"+str(n),10_000_000,"system_test")):
                    if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner=?",(name,)).fetchone():
                        self.e.create_company(name,city,cash,kind)
                self.features._treasury(city)
            if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner='system_import'").fetchone():
                self.e.create_company("system_import","Уфа",0,"system")
            if not self.e.db.execute("SELECT 1 FROM accounts WHERE owner='utility'").fetchone():
                self.e.create_company("utility","Уфа",0,"system")
        # AIManager.bootstrap handles its own account initialization.
        count=self.ai.bootstrap(100,2_000_000)
        with self.e.atomic():
            row=self.e.db.execute("SELECT 1 FROM beta_world WHERE id=1").fetchone()
            if not row:
                self.e.db.execute("INSERT INTO beta_world(id,last_tick_utc,enabled) VALUES(1,?,?)",
                                  (time.time(),1 if enable else 0))
        return {"agents":count,"clock":self.e.tick(),"seconds_per_day":GAME_DAY_SECONDS}

    def world_status(self):
        row=self.e.db.execute("SELECT * FROM beta_world WHERE id=1").fetchone()
        snapshot=self.e.db.execute("SELECT * FROM beta_daily_stats ORDER BY day DESC LIMIT 1").fetchone()
        return {
            "game_day":self.e.tick(),
            "year":self.e.tick()//365+1,
            "day_of_year":self.e.tick()%365+1,
            "seconds_per_day":round(GAME_DAY_SECONDS,3),
            "automated":bool(row["enabled"]) if row else False,
            "next_tick_utc":round(row["last_tick_utc"]+GAME_DAY_SECONDS) if row else None,
            "ai_companies":self.e.db.execute("SELECT COUNT(*) FROM ai_agents").fetchone()[0],
            "last_report":dict(snapshot) if snapshot else None,
            "money_supply_kopecks":self.e.total_money()
        }

    def _prepare_city_demand(self):
        day=self.e.tick()
        for city in CITIES:
            for sku in ("FOOD-035","FOOD-039"):
                row=self.e.db.execute("SELECT 1 FROM city_demand WHERE city=? AND sku=? AND day=?",
                                      (city,sku,day)).fetchone()
                if row is None:self.e.set_demand(city,sku,day,2_000_000,6)

    def _supply_market_makers(self):
        day=self.e.tick()
        for city_index,city in enumerate(CITIES):
            maker="market-maker-"+str(city_index)
            bids=self.e.db.execute("""SELECT sku,MAX(price) AS price,MIN(qty_left) AS qty
FROM market_orders WHERE city=? AND side='buy' AND status='open' AND owner!=?
GROUP BY sku ORDER BY sku LIMIT 40""",(city,maker)).fetchall()
            for ix,bid in enumerate(bids):
                sku=bid["sku"]
                if self.e.goods[sku]["source_mode"]=="manufacturing":continue
                qty=min(2500,int(bid["qty"]))
                if not qty:continue
                if self.e.db.execute("SELECT 1 FROM import_limits WHERE city=? AND sku=? AND day=?",
                    (city,sku,day)).fetchone() is None:
                    self.e.add_import_limit(city,sku,day,15000)
                try:
                    self.e.import_city(f"world:source:{day}:{city_index}:{ix}",
                        maker,sku,qty,int(self.prices.get(sku,12)))
                    offer=min(int(bid["price"]),int(self.prices.get(sku,12)))
                    self.e.place_order(f"world:offer:{day}:{city_index}:{ix}",
                        maker,sku,"sell",qty,max(1,offer))
                except ValueError:
                    # Finite import quota and money: maker can run out of liquidity.
                    continue

    def step(self):
        """One fully transactional tick; a second call is a new day, not a replay."""
        with self.e.atomic():
            before=self.e.total_money()
            day=self.e.tick()
            if self.e.db.execute("SELECT 1 FROM beta_daily_stats WHERE day=?",(day,)).fetchone():
                raise ValueError("Day already simulated")
            self._prepare_city_demand()
            report=self.ai.step(self.prices)
            self._supply_market_makers()
            trades=0
            for city in CITIES:
                for row in self.e.db.execute("SELECT DISTINCT sku FROM market_orders WHERE city=? AND status='open'",(city,)).fetchall():
                    trades+=len(self.e.match(city,row["sku"],max_trades=40))
            made=self.features.auto_produce()
            self.e.advance(1)
            delivered=self.features.deliver_freight()
            after=self.e.total_money()
            if before!=after:raise AssertionError("money-supply conservation violated")
            self.e.db.execute("""INSERT INTO beta_daily_stats(day,ai_decisions,trades,produced,delivered,cash_supply,note)
VALUES(?,?,?,?,?,?,?)""",(day,report["actions"],trades,made,delivered,after,"beta prototype, limited AI recipes"))
            return {"day":day,"trades":trades,"ai_actions":report["actions"],
                    "automatic_batches":made,"delivered":delivered,"money_conserved":True}

    def run_due(self,now=None,max_days=2):
        """Called by a server-local scheduler, not a public HTTP endpoint."""
        now=time.time() if now is None else float(now)
        summaries=[]
        with self.e.atomic():
            row=self.e.db.execute("SELECT * FROM beta_world WHERE id=1").fetchone()
            if not row or not row["enabled"]:return summaries
            if now<row["last_tick_utc"]+GAME_DAY_SECONDS:return summaries
            pending=min(int((now-row["last_tick_utc"])//GAME_DAY_SECONDS),max_days)
            for _ in range(pending):
                summaries.append(self.step())
                self.e.db.execute("UPDATE beta_world SET last_tick_utc=last_tick_utc+? WHERE id=1",
                    (GAME_DAY_SECONDS,))
        return summaries
