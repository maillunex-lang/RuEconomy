"""Expanded beta mechanics: test with isolated SQLite, never live-world data."""
import unittest
from core.market import Market
from core.beta_features import BetaFeatures
from core.world import WorldEngine

class FeaturesTests(unittest.TestCase):
    def setUp(self):
        self.e=Market()
        self.e.db.executescript("""
CREATE TABLE buildings(
id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,enterprise_id TEXT NOT NULL,
city TEXT NOT NULL,x INTEGER NOT NULL,y INTEGER NOT NULL,created_tick INTEGER NOT NULL,
UNIQUE(city,x,y));
""")
        self.b=BetaFeatures(self.e)
        for name,city,cash in (("seller","Уфа",10_000_000),("buyer","Москва",10_000_000),
                               ("other","Уфа",10_000_000),("household:Уфа","Уфа",1000000),
                               ("system_import","Уфа",0),("utility","Уфа",0)):
            self.e.create_company(name,city,cash)
    def tearDown(self):self.e.close()
    def build(self,owner,ent,x,y,city=None,size=1,op=None):
        return self.b.build(owner,ent,city or self.e._company_city(owner),x,y,size,
                            op or f"build:{owner}:{ent}:{x}:{y}",{ent})
    def test_build_rectangles_and_replay(self):
        a=self.build("seller","ENT-001",1,1,size=2)
        self.assertEqual(a["size"],2)
        self.assertEqual(self.build("seller","ENT-001",1,1,size=2)["id"],a["id"])
        with self.assertRaisesRegex(ValueError,"занят"):
            self.build("other","ENT-041",2,2)
        b=self.build("other","ENT-041",3,3)
        self.assertNotEqual(a["id"],b["id"])
    def test_build_wrong_city_bounds_or_size(self):
        with self.assertRaises(ValueError):self.build("seller","ENT-001",23,15,size=3)
        with self.assertRaises(ValueError):self.build("seller","ENT-001",0,0,size=4)
    def test_harvest_reserve_cap_and_monetary_conservation(self):
        bid=self.build("seller","ENT-001",1,1)["id"]
        initial=self.e.total_money()
        a=self.b.harvest("seller",bid,"AGRI-001",2000,"harvest:0001")
        self.assertEqual(a["remaining"],198000)
        self.assertEqual(self.b.harvest("seller",bid,"AGRI-001",2000,"harvest:0001"),a)
        with self.assertRaisesRegex(ValueError,"мощность"):
            self.b.harvest("seller",bid,"AGRI-001",4000,"harvest:0002")
        self.assertEqual(self.e.inventory("seller","AGRI-001"),2000)
        self.assertEqual(initial,self.e.total_money())
    def test_harvest_requires_compatible_site(self):
        bid=self.build("seller","ENT-041",1,1)["id"]
        with self.assertRaises(ValueError):self.b.harvest("seller",bid,"AGRI-001",10,"harvest:bad")
    def test_upgrade_improves_daily_source_capacity(self):
        bid=self.build("seller","ENT-001",1,1)["id"]
        a=self.b.upgrade("seller",bid,"upgrade:001")
        self.assertEqual(a["level"],2)
        self.assertEqual(self.b.upgrade("seller",bid,"upgrade:001"),a)
        self.b.harvest("seller",bid,"AGRI-001",10000,"harvest:upgraded")
    def test_market_trade_and_reserved_funds(self):
        bid=self.build("seller","ENT-001",1,1)["id"]
        self.b.harvest("seller",bid,"AGRI-001",2000,"harvest:mkt")
        b=self.b.place("other","order:buy:1","AGRI-001","buy",100,30)
        s=self.b.place("seller","order:sell:1","AGRI-001","sell",100,25)
        self.assertEqual(s["matched"],1)
        self.assertEqual(self.e.inventory("other","AGRI-001"),100)
        self.assertEqual(self.e.inventory("seller","AGRI-001"),1900)
    def test_contract_ownership(self):
        bid=self.build("seller","ENT-001",1,1)["id"]
        self.b.harvest("seller",bid,"AGRI-001",100,"harvest:contract")
        self.b.create_contract("other","contract:0001","seller","AGRI-001",30,50)
        with self.assertRaises(ValueError):self.b.fulfill_contract("other","contract:0001")
        self.b.fulfill_contract("seller","contract:0001")
        self.assertEqual(self.e.inventory("other","AGRI-001"),30)
    def test_freight_requires_buyer_request_and_arrival(self):
        bid=self.build("seller","ENT-001",1,1)["id"]
        self.b.harvest("seller",bid,"AGRI-001",100,"harvest:freight")
        before=self.e.total_money()
        a=self.b.freight_request("buyer","freight:0001","seller","AGRI-001",20,100)
        self.assertEqual(a["status"],"requested")
        with self.assertRaises(ValueError):self.b.freight_accept("buyer","freight:0001")
        a=self.b.freight_accept("seller","freight:0001")
        self.assertEqual(a["status"],"transit")
        self.assertEqual(self.e.inventory("buyer","AGRI-001"),0)
        self.assertEqual(self.b.deliver_freight(),0)
        self.e.advance(1)
        self.assertEqual(self.b.deliver_freight(),1)
        self.assertEqual(self.b.deliver_freight(),0)
        self.assertEqual(self.e.inventory("buyer","AGRI-001"),20)
        self.assertEqual(before,self.e.total_money())
    def test_retail_requires_shop_and_budget(self):
        farm=self.build("seller","ENT-001",0,0)["id"]
        self.b.harvest("seller",farm,"AGRI-001",50,"harvest:shop")
        shop=self.build("seller","ENT-041",3,0)["id"]
        before=self.e.total_money()
        a=self.b.retail("seller",shop,"AGRI-001",4,25,"retail:0001")
        self.assertEqual(a["revenue"],100)
        self.assertEqual(self.b.retail("seller",shop,"AGRI-001",4,25,"retail:0001"),a)
        with self.assertRaises(ValueError):self.b.retail("seller",farm,"AGRI-001",2,25,"retail:bad")
        self.assertEqual(self.e.total_money(),before)
    def test_player_production_across_catalog(self):
        b=self.build("seller","ENT-007",1,1)["id"]
        recipes=[r for r in self.e.recipes.values() if r["enterprise_id"]=="ENT-007" and all(
             self.e.goods[i["goods_id"]]["source_mode"]!="manufacturing" for i in r["inputs"])]
        self.assertTrue(recipes)
        r=recipes[0]
        for item in r["inputs"]:
            self.e._lot("seller",item["goods_id"],item["quantity"],item["quantity"])
        self.e.produce_at("production:test","seller","building:"+str(b),r["recipe_id"])
        self.assertGreater(self.e.inventory("seller",r["output_goods_id"]),0)

class WorldTests(unittest.TestCase):
    def setUp(self):
        self.e=Market()
        self.e.db.executescript("""
CREATE TABLE buildings(id INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT,enterprise_id TEXT,
city TEXT,x INTEGER,y INTEGER,created_tick INTEGER,UNIQUE(city,x,y));
""")
        self.b=BetaFeatures(self.e)
        self.w=WorldEngine(self.e,self.b)
    def tearDown(self):self.e.close()
    def test_bootstrap_no_double_issuance(self):
        a=self.w.bootstrap(enable=False)
        total=self.e.total_money()
        b=self.w.bootstrap(enable=False)
        self.assertEqual(a["agents"],100)
        self.assertEqual(b["agents"],100)
        self.assertEqual(self.e.total_money(),total)
        self.assertEqual(len(self.w.ai.e.goods),300)
    def test_world_tick_conserves_money_and_advances(self):
        self.w.bootstrap(enable=False)
        before=self.e.total_money()
        day=self.w.step()
        self.assertEqual(day["day"],0)
        self.assertEqual(self.e.tick(),1)
        self.assertTrue(day["money_conserved"])
        self.assertEqual(before,self.e.total_money())
    def test_scheduler_due_exactly_once(self):
        self.w.bootstrap(enable=True)
        anchor=self.e.db.execute("SELECT last_tick_utc FROM beta_world WHERE id=1").fetchone()[0]
        from core.beta_features import GAME_DAY_SECONDS
        self.assertEqual(self.w.run_due(anchor+GAME_DAY_SECONDS-.5),[])
        self.assertEqual(len(self.w.run_due(anchor+GAME_DAY_SECONDS+1)),1)
        self.assertEqual(self.e.tick(),1)
        self.assertEqual(self.w.run_due(anchor+GAME_DAY_SECONDS+1),[])
    def test_five_day_economy_makes_real_trades_and_products(self):
        self.w.bootstrap(enable=False)
        for _ in range(5):self.w.step()
        self.assertGreater(self.e.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0],0)
        self.assertGreater(self.e.db.execute("SELECT COUNT(*) FROM events WHERE kind LIKE 'production:%'").fetchone()[0],0)
    def test_calendar_seven_days_equal_game_year(self):
        from core.beta_features import GAME_DAY_SECONDS
        self.assertAlmostEqual(GAME_DAY_SECONDS*365,7*86400,places=4)

if __name__=="__main__":unittest.main()
