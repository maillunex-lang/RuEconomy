import unittest
from core.market import Market
class MarketTests(unittest.TestCase):
 def setUp(self):
  self.e=Market()
  for x,city,cash in [('seller','Уфа',100000),('buyer','Уфа',100000),('buyer2','Уфа',100000),('outside','Москва',100000),('house','Уфа',100000),('system_import','Уфа',0),('utility','Уфа',0)]:
   self.e.create_company(x,city,cash)
  self.e.import_goods('seed','seller','AGRI-001',100,1,100)
 def tearDown(self):self.e.close()
 def test_order_match_and_conservation(self):
  before=self.e.total_money()
  self.e.place_order('s','seller','AGRI-001','sell',30,12)
  self.e.place_order('b','buyer','AGRI-001','buy',20,15)
  x=self.e.match('Уфа','AGRI-001')
  self.assertEqual(len(x),1);self.assertEqual(x[0]['qty'],20)
  self.assertEqual(self.e.inventory('buyer','AGRI-001'),20)
  self.assertEqual(self.e._order('s')['qty_left'],10)
  self.assertEqual(self.e.total_money(),before)
  self.assertEqual(self.e.match('Уфа','AGRI-001'),[])
 def test_cross_city_blocked(self):
  with self.assertRaises(ValueError):self.e.place_order('r','outside','AGRI-001','buy',1,10,city='Уфа')
 def test_reservation_prevents_double_sell(self):
  self.e.place_order('s','seller','AGRI-001','sell',80,2)
  with self.assertRaises(ValueError):self.e.place_order('s2','seller','AGRI-001','sell',30,2)
 def test_cancel_frees_reserved_stock(self):
  self.e.place_order('s','seller','AGRI-001','sell',80,2)
  self.e.cancel_order('s','seller')
  self.e.place_order('s2','seller','AGRI-001','sell',100,2)
 def test_reserved_cash(self):
  self.e.place_order('b','buyer','AGRI-001','buy',100,800)
  with self.assertRaises(ValueError):self.e.place_order('b2','buyer','AGRI-001','buy',100,800)
 def test_quota_and_replay(self):
  self.e.add_import_limit('Уфа','RAW-025',0,20)
  a=self.e.import_city('water','buyer','RAW-025',10,1)
  self.assertEqual(a,self.e.import_city('water','buyer','RAW-025',10,1))
  with self.assertRaises(ValueError):self.e.import_city('more','buyer','RAW-025',11,1)
  self.assertEqual(self.e.inventory('buyer','RAW-025'),10)
 def test_demand_bounded(self):
  self.e.set_demand('Уфа','AGRI-001',0,100,5)
  self.e.household_purchase('h1','Уфа','AGRI-001','seller',5,20,'house')
  with self.assertRaises(ValueError):self.e.household_purchase('h2','Уфа','AGRI-001','seller',1,20,'house')
 def test_no_self_match(self):
  self.e.place_order('s','seller','AGRI-001','sell',10,10)
  self.e.place_order('b','seller','AGRI-001','buy',10,15)
  self.assertEqual(self.e.match('Уфа','AGRI-001'),[])
if __name__=='__main__':unittest.main()
