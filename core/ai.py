"""M2: deterministic AI companies with funded purchasing, real production and retail."""
from __future__ import annotations
import random
from .market import Market,CITIES

class AIManager:
    def __init__(self,market:Market,seed:int=42):
        self.e=market
        self.seed=seed
        self.e.db.executescript("""
CREATE TABLE IF NOT EXISTS ai_agents(
 id TEXT PRIMARY KEY,city TEXT NOT NULL,role TEXT NOT NULL,
 goods_id TEXT NOT NULL,risk_bps INTEGER NOT NULL,ambition_bps INTEGER NOT NULL,
 decisions INTEGER NOT NULL DEFAULT 0,cash_start INTEGER NOT NULL,
 FOREIGN KEY(id) REFERENCES companies(id));
CREATE TABLE IF NOT EXISTS ai_decisions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,agent TEXT NOT NULL,tick INTEGER NOT NULL,
 action TEXT NOT NULL,reason TEXT NOT NULL,success INTEGER NOT NULL,
 FOREIGN KEY(agent) REFERENCES ai_agents(id));
""")
        self.e.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ai_decision_per_day ON ai_decisions(agent,tick)")
    def bootstrap(self,count:int=100,initial_cash:int=2_000_000):
        if type(count)!=int or count<1 or type(initial_cash)!=int or initial_cash<=0:
            raise ValueError("invalid bootstrap")
        resources=sorted(c for c,g in self.e.goods.items() if g["source_mode"]!="manufacturing")
        rng=random.Random(self.seed)
        for i in range(count):
            aid=f"ai-{i:04d}"
            if self.e.db.execute("SELECT 1 FROM ai_agents WHERE id=?",(aid,)).fetchone():
                continue
            city=CITIES[i%len(CITIES)]
            role=("trader","retailer","producer")[i%3]
            sku=resources[i%len(resources)] if role=="trader" else ("FOOD-035" if i%len(CITIES)%2 else "FOOD-039")
            self.e.create_company(aid,city,initial_cash,"ai")
            if role=="producer":
                # MVP starter milling facility granted as explicitly modeled initial endowment.
                self.e.create_facility("plant:"+aid,aid,"ENT-007",1)
            self.e.db.execute("INSERT INTO ai_agents(id,city,role,goods_id,risk_bps,ambition_bps,cash_start) VALUES(?,?,?,?,?,?,?)",
                (aid,city,role,sku,rng.randint(2000,8500),rng.randint(1000,8500),initial_cash))
        return self.e.db.execute("SELECT COUNT(*) FROM ai_agents").fetchone()[0]
    def _note(self,aid,action,reason,success):
        self.e.db.execute("INSERT INTO ai_decisions(agent,tick,action,reason,success) VALUES(?,?,?,?,?)",
            (aid,self.e.tick(),action,reason,int(success)))
        self.e.db.execute("UPDATE ai_agents SET decisions=decisions+1 WHERE id=?",(aid,))
    def _recipe(self,sku):
        match=[r for r in self.e.recipes.values() if r["output_goods_id"]==sku]
        return min(match,key=lambda r:r["recipe_id"])
    def _hold(self,aid,reason):
        self._note(aid,"hold",reason,True)
        return {"id":aid,"actions":["hold"]}
    def act(self,aid,prices):
        seen=self.e.db.execute("SELECT action FROM ai_decisions WHERE agent=? AND tick=?",(aid,self.e.tick())).fetchone()
        if seen:return {"id":aid,"actions":[seen[0]],"replayed":True}
        r=self.e.db.execute("SELECT * FROM ai_agents WHERE id=?",(aid,)).fetchone()
        if r is None:raise ValueError("unknown AI agent")
        sku=r["goods_id"];day=self.e.tick();stock=self.e.inventory(aid,sku)
        price=max(1,int(prices.get(sku,100)))
        risk=int(r["risk_bps"]);ambition=int(r["ambition_bps"])
        role=r["role"]
        try:
            if role=="producer":
                if stock<=0:
                    recipe=self._recipe(sku)
                    needed={}
                    for x in recipe["inputs"]:
                        needed[x["goods_id"]]=needed.get(x["goods_id"],0)+x["quantity"]
                    missing={x:max(0,n-self.e.inventory(aid,x)) for x,n in needed.items()}
                    if any(missing.values()):
                        count=0
                        for good,qty in missing.items():
                            if qty==0:continue
                            # Do not post duplicate bids when yesterday's bid is still open.
                            open_qty=self.e.db.execute("""SELECT COALESCE(SUM(qty_left),0) FROM market_orders
                            WHERE owner=? AND sku=? AND side='buy' AND status='open'""",(aid,good)).fetchone()[0]
                            qty=max(0,qty-open_qty)
                            if not qty:continue
                            inp_price=max(1,int(prices.get(good,12)))
                            bid=inp_price*(10800+int(risk/20))//10000
                            if qty*bid>self.e.balance(aid)-self.e._reserved_purchase_funds(aid):
                                continue
                            self.e.place_order(f"ai:{aid}:{day}:inputs:{good}",aid,good,"buy",qty,bid)
                            count+=1
                        self._note(aid,"source_inputs",f"buying {count} material inputs, no free inventory",True)
                        return {"id":aid,"actions":["source_inputs"],"pending":count}
                    prod=self.e.produce_at(f"ai:{aid}:{day}:produce",aid,"plant:"+aid,recipe["recipe_id"])
                    stock=self.e.inventory(aid,sku)
                    self._note(aid,"produce",f"one real batch, cost {prod['cost']} kopecks",True)
                    return {"id":aid,"actions":["produce"]}
                # Offer stock only once. No free supply.
                qty=max(0,stock-self.e._reserved_sale_qty(aid,sku))
                if qty:
                    ask=max(1,price*(9600+int(ambition/30))//10000)
                    self.e.place_order(f"ai:{aid}:{day}:sell",aid,sku,"sell",qty,ask)
                    self._note(aid,"sell","selling produced flour",True)
                    return {"id":aid,"actions":["sell"]}
                return self._hold(aid,"finished product already listed")
            if role=="retailer":
                if stock>0:
                    household="household:"+r["city"]
                    exists=self.e.db.execute("SELECT 1 FROM companies WHERE id=?",(household,)).fetchone()
                    if exists:
                        offer=max(1,price*12500//10000)
                        try:
                            outcome=self.e.household_purchase(
                                f"ai:{aid}:{day}:household",r["city"],sku,aid,1,offer,household)
                            self._note(aid,"retail_sale",f"household paid {outcome['paid']} kopecks",True)
                            return {"id":aid,"actions":["retail_sale"]}
                        except ValueError:
                            return self._hold(aid,"household budget or demand exhausted")
                    return self._hold(aid,"no household buyer in standalone test")
                existing=self.e.db.execute("""SELECT COALESCE(SUM(qty_left),0) FROM market_orders
                    WHERE owner=? AND sku=? AND side='buy' AND status='open'""",(aid,sku)).fetchone()[0]
                if existing:return self._hold(aid,"retail purchase order already active")
                bid=max(1,price*(11200+int(risk/20))//10000)
                if self.e.balance(aid)-self.e._reserved_purchase_funds(aid)<bid:
                    return self._hold(aid,"retailer lacks cash")
                self.e.place_order(f"ai:{aid}:{day}:buy",aid,sku,"buy",1,bid)
                self._note(aid,"buy","bounded retailer wholesale demand",True)
                return {"id":aid,"actions":["buy"]}
            # Traders take limited inventory positions and face real purchase costs.
            if stock>0:
                qty=max(0,min(stock,10)-self.e._reserved_sale_qty(aid,sku))
                if qty:
                    ask=max(1,price*(10000+ambition//16)//10000)
                    self.e.place_order(f"ai:{aid}:{day}:sell",aid,sku,"sell",qty,ask)
                    self._note(aid,"sell","bounded inventory offer",True)
                    return {"id":aid,"actions":["sell"]}
                return self._hold(aid,"existing sell offer active")
            existing=self.e.db.execute("""SELECT COALESCE(SUM(qty_left),0) FROM market_orders
                WHERE owner=? AND sku=? AND side='buy' AND status='open'""",(aid,sku)).fetchone()[0]
            if existing:return self._hold(aid,"already bidding")
            bid=max(1,price*(11000-risk//20)//10000)
            qty=min(10,(self.e.balance(aid)-self.e._reserved_purchase_funds(aid))//(bid*2))
            if qty<=0:return self._hold(aid,"not enough cash")
            self.e.place_order(f"ai:{aid}:{day}:buy",aid,sku,"buy",qty,bid)
            self._note(aid,"buy","risk-limited inventory acquisition",True)
            return {"id":aid,"actions":["buy"]}
        except ValueError as exc:
            self._note(aid,"hold",f"blocked by real economic constraint: {exc}",False)
            return {"id":aid,"actions":["hold"],"reason":str(exc)}
    def step(self,prices):
        agents=[r[0] for r in self.e.db.execute("SELECT id FROM ai_agents ORDER BY id")]
        out=[self.act(a,prices) for a in agents]
        counts={}
        for r in out:
            for action in r["actions"]:counts[action]=counts.get(action,0)+1
        return {"day":self.e.tick(),"agents":len(out),"actions":sum(len(r["actions"]) for r in out),"by_action":counts}
