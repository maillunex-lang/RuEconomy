"""Economy Balancing 1.1: recompute reference costs from draft-2 and identify outliers.
All rates are explicit gameplay assumptions, not observed Russian market prices."""
from pathlib import Path
import json,csv,collections
D=Path(__file__).resolve().parents[1]/"docs"
def ceildiv(a,b):return (a+b-1)//b
def run():
 G={g["goods_id"]:g for g in json.loads((D/"PRODUCTION-CATALOG-1.0-GOODS.json").read_text())["goods"]}
 R=json.loads((D/"PRODUCTION-CATALOG-1.0-RECIPES.json").read_text())["recipes"]
 scenarios={
 "baseline":{"source_bps":10000,"electricity_kop_kwh":900,"labor_kop_min":45,"water_kop_kg":3,"wear_bps":400,"logistics_bps":300,"overhead_bps":500},
 "supply_shock":{"source_bps":14000,"electricity_kop_kwh":1300,"labor_kop_min":50,"water_kop_kg":4,"wear_bps":550,"logistics_bps":800,"overhead_bps":650},
 "productivity":{"source_bps":10000,"electricity_kop_kwh":850,"labor_kop_min":35,"water_kop_kg":3,"wear_bps":300,"logistics_bps":250,"overhead_bps":400}}
 result={}
 for name,cfg in scenarios.items():
  prices={c:ceildiv((18 if c.startswith("AGRI-") else 12)*cfg["source_bps"],10000) for c,g in G.items() if g["source_mode"]!="manufacturing"}
  rows=[];group=collections.defaultdict(list)
  for r in sorted(R,key=lambda r:G[r["output_goods_id"]]["processing_tier"]):
   assert all(i["goods_id"] in prices for i in r["inputs"]),(r["recipe_id"],"unpriced")
   material=sum(prices[i["goods_id"]]*i["quantity"] for i in r["inputs"])
   electricity=ceildiv(r["electricity_wh"]*cfg["electricity_kop_kwh"],1000)
   labor=r["labor_minutes"]*cfg["labor_kop_min"]
   water=ceildiv(r["water_g_utility"]*cfg["water_kop_kg"],1000)
   direct=material+electricity+labor+water
   wear=ceildiv(direct*cfg["wear_bps"],10000)
   logistics=ceildiv(material*cfg["logistics_bps"],10000)
   overhead=ceildiv(direct*cfg["overhead_bps"],10000)
   total=direct+wear+logistics+overhead
   unit=ceildiv(total,r["outputs"][0]["quantity"])
   row={"recipe_id":r["recipe_id"],"goods_id":r["output_goods_id"],"variant":r["process_variant"],"batch_qty":r["outputs"][0]["quantity"],"material_kopecks":material,"electricity_kopecks":electricity,"labor_kopecks":labor,"water_kopecks":water,"wear_kopecks":wear,"logistics_kopecks":logistics,"overhead_kopecks":overhead,"batch_cost_kopecks":total,"unit_cost_kopecks":unit}
   rows.append(row);group[r["output_goods_id"]].append(row)
   if len(group[r["output_goods_id"]])==G[r["output_goods_id"]]["recipe_count"]:
    prices[r["output_goods_id"]]=min(z["unit_cost_kopecks"] for z in group[r["output_goods_id"]])
  assert len(prices)==300 and len(rows)==450
  with (D/f"ECONOMY-BALANCING-1.1-COSTS-{name}.csv").open("w",newline="",encoding="utf-8") as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
  result[name]={"prices":prices,"rows":rows}
 assert all(result["supply_shock"]["prices"][c]>=result["baseline"]["prices"][c] for c in G)
 outliers=sorted(result["baseline"]["rows"],key=lambda x:x["unit_cost_kopecks"],reverse=True)[:15]
 # Enterprise parameters: explicitly illustrative initial values for 45 types.
 enterprises=json.loads((D/"PRODUCTION-CATALOG-1.0-EQUIPMENT.json").read_text())["enterprises"]
 enterprise_params=[]
 for ent in enterprises:
  typ=ent["enterprise_id"]
  i=int(typ.split("-")[1])
  enterprise_params.append({"enterprise_id":typ,"illustrative_capex_kopecks":(5000000+i*100000)*100,"illustrative_daily_fixed_opex_kopecks":(3000+i*100)*100,"max_parallel_batches":1,"line_count":len(ent["lines"]),"utilization_limit_bps":9000,"monthly_depreciation_bps":100,"status":"illustrative_not_calibrated"})
 assert len(enterprise_params)==45
 with (D/"ECONOMY-BALANCING-1.1-ENTERPRISE-PARAMETERS.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(enterprise_params[0]));w.writeheader();w.writerows(enterprise_params)
 manifest={"version":"1.1","catalog_version":"1.0-draft-2","scenarios":scenarios,"goods":300,"recipes":450,"enterprises":45,"reference_unit":"integer kopecks","scenario_calculations_passed":True,"shock_monotonicity_passed":True,"capex_opex_status":"illustrative not empirically calibrated","top_cost_outliers":outliers,"open_risks":["industry BOM yields and byproducts not audited","wages/capex/tariffs are illustrative","household budget and elasticity not measured","city importer quotas uncalibrated","10-city 100-AI market not simulated"],"not_real_world_prices":True}
 (D/"ECONOMY-BALANCING-1.1-VALIDATION.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
 (D/"ECONOMY-BALANCING-1.1.md").write_text("# Economy Balancing 1.1\n\n"
 "**Статус: модельные расчёты по каталогу 1.0-draft-2, не окончательная экономическая калибровка.**\n\n"
 "Сформированы 1350 расчётов (450 рецептов × 3 сценария) в целых копейках. Стоимость ингредиентов рекурсивно определяется через граф рецептов. "
 "Расходы: материалы, энергия, труд, вода, износ, логистика, накладные. Проверена монотонность при шоке сырья.\n\n"
 "В файле ENTERPRISE-PARAMETERS.csv приведены **условные**, а не фактические CAPEX/OPEX для 45 предприятий, коэффициенты загрузки и амортизации. "
 "Цены, мощность и нормы не проверены на реальных предприятиях. Прибыльность без реального спроса не подтверждена.\n\n"
 "Не выполнены: модель потребителей 10 городов, 100 ИИ-компаний, банкротства, реальные региональные зарплаты и импортные квоты. "
 "Тестовый M0 ниже не следует считать MMO-сервером.\n\n"
 "Артефакты: ECONOMY-BALANCING-1.1-COSTS-{baseline,supply_shock,productivity}.csv, "
 "ECONOMY-BALANCING-1.1-ENTERPRISE-PARAMETERS.csv, ECONOMY-BALANCING-1.1-VALIDATION.json.\n")
 print(json.dumps({"status":"PASS","recipes":450,"scenarios":3,"enterprises":45,"outliers":len(outliers)},ensure_ascii=False))
if __name__=="__main__":run()
