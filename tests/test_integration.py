import unittest
from core.market import Market
from simulate import run

class SafeguardTests(unittest.TestCase):
    def setUp(self):
        self.e=Market()
        for id,city,balance in [
            ("seller","Уфа",100000),("buyer","Уфа",100000),("house","Уфа",100000),
            ("utility","Уфа",0),("system_import","Уфа",0)]:
            self.e.create_company(id,city,balance)
        self.e.import_goods("init","seller","AGRI-001",100,10,100)
    def tearDown(self):self.e.close()
    def test_goods_are_reserved_against_direct_trade(self):
        self.e.place_order("ask","seller","AGRI-001","sell",80,20)
        with self.assertRaisesRegex(ValueError,"reserved"):
            self.e.trade("direct","buyer","seller","AGRI-001",30,20)
        self.assertEqual(self.e.inventory("seller","AGRI-001"),100)
        self.e.cancel_order("ask","seller")
        self.e.trade("direct","buyer","seller","AGRI-001",30,20)
        self.assertEqual(self.e.inventory("seller","AGRI-001"),70)
    def test_cash_is_reserved_against_direct_trade(self):
        self.e.place_order("bid","buyer","AGRI-001","buy",100,900)
        with self.assertRaisesRegex(ValueError,"reserved"):
            self.e.trade("direct","buyer","seller","AGRI-001",50,300)
        self.assertEqual(self.e.balance("buyer"),100000)
    def test_cash_is_reserved_against_import(self):
        self.e.place_order("bid","buyer","AGRI-001","buy",100,900)
        with self.assertRaisesRegex(ValueError,"reserved"):
            self.e.import_goods("imp","buyer","RAW-025",1000,20,1000)
    def test_replay_import_after_quota_consumed(self):
        self.e.add_import_limit("Уфа","RAW-025",0,10)
        a=self.e.import_city("import","buyer","RAW-025",10,2)
        self.assertEqual(self.e.import_city("import","buyer","RAW-025",10,2),a)
        self.assertEqual(self.e.inventory("buyer","RAW-025"),10)
        self.assertEqual(self.e.db.execute("SELECT used FROM import_limits").fetchone()[0],10)
    def test_replay_household_purchase_after_demand_consumed(self):
        self.e.set_demand("Уфа","AGRI-001",0,100,5)
        a=self.e.household_purchase("buy","Уфа","AGRI-001","seller",5,20,"house")
        self.assertEqual(self.e.household_purchase("buy","Уфа","AGRI-001","seller",5,20,"house"),a)
        self.assertEqual(self.e.inventory("house","AGRI-001"),5)
        self.assertEqual(self.e.db.execute("SELECT qty_bought FROM city_demand").fetchone()[0],5)

class OfflineIntegrationTests(unittest.TestCase):
    def test_14_game_days_reproducible(self):
        a=run(days=14,seed=42)
        b=run(days=14,seed=42)
        self.assertEqual(a,b)
        self.assertEqual(a["cities"],10)
        self.assertEqual(a["ai_agents"],100)
        self.assertEqual(a["ai_decisions"],1400)
        self.assertGreater(a["traded_quantity"],0)
        self.assertGreater(a["produced_batches"],0)
        self.assertGreater(a["household_purchases"],0)
        self.assertTrue(a["money_conserved"])
    def test_different_seed_still_conserves_money(self):
        a=run(days=7,seed=17)
        self.assertEqual(a["cities"],10)
        self.assertTrue(a["money_conserved"])
        self.assertGreater(a["produced_batches"],0)

if __name__=="__main__":unittest.main()
