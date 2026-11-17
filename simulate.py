"""M3 offline integration simulation (no services, no network, no user data)."""
from __future__ import annotations
import argparse,json,csv
from pathlib import Path
from core.market import Market,CITIES
from core.ai import AIManager

ROOT=Path(__file__).resolve().parent
def run(days:int=14,seed:int=42,output=None):
 if type(days)!=int or days<1 or days>365:raise ValueError("days 1..365")
 e=Market()
 ai=AIManager(e,seed)
 count=ai.bootstrap(100,initial_cash=2_000_000)
 for city in CITIES:
  e.create_company("market-maker-"+str(CITIES.index(city)),city,10_000_000,"system_test")
 for city in CITIES:
  e.create_company("household:"+city,city,20_000_000,"households")
 e.create_company("system_import","Уфа",0)
 e.create_company("utility","Уфа",0)
 # Model prices are illustrative. Primary products sourced from finite daily quotas.
 reference={c:(18 if c.startswith("AGRI") else 12) for c in e.goods}
 with (ROOT/"docs/ECONOMY-BALANCING-1.1-COSTS-baseline.csv").open(encoding="utf-8") as f:
  for row in csv.DictReader(f):
   sku=row["goods_id"]
   if e.goods[sku]["source_mode"]=="manufacturing":
    cost=int(row["unit_cost_kopecks"])
    reference[sku]=min(cost,reference[sku]) if reference[sku]>12 else cost
 report={"version":"M3-preproduction-offline","seed":seed,"cities":len(CITIES),"ai_agents":count,
         "days":days,"daily":[],"limitations":["starter milling facilities are given as initial endowment","no population budget distributions","no market-making money issuance","prices are illustrative","system test market makers trade for liquidity"]}
 money_initial=e.total_money()
 total_volume=0
 for day in range(days):
  for city in CITIES:
   for sku in ("FOOD-035","FOOD-039"):
    e.set_demand(city,sku,day,2_000_000,6)
  decisions=ai.step(reference)
  # Market-makers only replenish against actual AI bids, with finite city/day quotas.
  # Each purchase is funded from a previously created account, never from an infinite tap.
  for city_index,city in enumerate(CITIES):
   maker="market-maker-"+str(city_index)
   bids=e.db.execute("""SELECT sku,MAX(price) AS price,MIN(qty_left) AS qty
                         FROM market_orders
                         WHERE city=? AND side='buy' AND status='open'
                         GROUP BY sku ORDER BY sku""",(city,)).fetchall()
   for ix,bid in enumerate(bids):
    product=bid["sku"]
    if e.goods[product]["source_mode"]=="manufacturing":continue
    wanted=min(2500,int(bid["qty"]))
    if not wanted:continue
    # Ensure the maker has sufficient unreserved stock before submitting its order.
    # Bounded 10 000-unit source quota per city/SKU/day is illustrative.
    if e.db.execute("SELECT 1 FROM import_limits WHERE city=? AND sku=? AND day=?",
                    (city,product,day)).fetchone() is None:
     e.add_import_limit(city,product,day,10000)
    try:
     e.import_city(f"m3-import:{day}:{city_index}:{ix}",maker,product,wanted,reference[product])
    except ValueError:continue
    offer=max(1,min(int(bid["price"]),reference[product]))
    try:e.place_order(f"m3-sell:{day}:{city_index}:{ix}",maker,product,"sell",wanted,offer)
    except ValueError:continue
  volume=0
  for city in CITIES:
   products=e.db.execute("SELECT DISTINCT sku FROM market_orders WHERE city=? AND status='open'",(city,)).fetchall()
   for p in products:
    matched=e.match(city,p[0])
    volume+=sum(x["qty"] for x in matched)
  total_volume+=volume
  report["daily"].append({"day":day,"decisions":decisions["actions"],"traded_qty":volume,
                          "money_supply":e.total_money(),
                          "open_orders":e.db.execute("SELECT COUNT(*) FROM market_orders WHERE status='open'").fetchone()[0]})
  if e.total_money()!=money_initial:raise AssertionError("money not conserved day "+str(day))
  e.advance(1)
 assert total_volume>0,"market integration produced zero trades"
 produced=e.db.execute("SELECT COUNT(*) FROM events WHERE kind LIKE 'production:%'").fetchone()[0]
 household_sales=e.db.execute("SELECT COUNT(*) FROM ai_decisions WHERE action='retail_sale' AND success=1").fetchone()[0]
 assert produced>0,"AI producers did not produce"
 assert household_sales>0,"household demand never purchased"
 report["produced_batches"]=produced
 report["household_purchases"]=household_sales
 report["ai_roles"]={r[0]:r[1] for r in e.db.execute("SELECT role,COUNT(*) FROM ai_agents GROUP BY role")}
 report["produced_reference_goods"]=["FOOD-035","FOOD-039"]
 report["wages_paid_kopecks"]=e.db.execute(
     "SELECT COALESCE(SUM(amount),0) FROM transfers WHERE operation LIKE '%:wages'").fetchone()[0]
 report["household_spending_kopecks"]=e.db.execute(
     "SELECT COALESCE(SUM(spent_kopecks),0) FROM city_demand").fetchone()[0]
 report["open_orders_end"]=e.db.execute(
     "SELECT COUNT(*) FROM market_orders WHERE status='open'").fetchone()[0]
 report["traded_quantity"]=total_volume
 report["money_supply_initial"]=money_initial
 report["money_supply_final"]=e.total_money()
 report["money_conserved"]=money_initial==e.total_money()
 report["trade_events"]=e.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
 report["ai_decisions"]=e.db.execute("SELECT COUNT(*) FROM ai_decisions").fetchone()[0]
 report["final_cash_min"]=e.db.execute("SELECT MIN(balance) FROM accounts").fetchone()[0]
 report["status"]="PASS: deterministic bounded offline integration smoke"
 e.close()
 if output:
  Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 return report
if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--days",type=int,default=14)
 parser.add_argument("--seed",type=int,default=42)
 parser.add_argument("--output",default=str(ROOT/"docs/ECONOMIC-M3-SIMULATION.json"))
 a=parser.parse_args()
 r=run(a.days,a.seed,a.output)
 print(json.dumps({k:v for k,v in r.items() if k!="daily"},ensure_ascii=False,indent=2))
