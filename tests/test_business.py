import unittest
from core.economy import Economy
class BusinessTests(unittest.TestCase):
 def setUp(self):
  self.e=Economy()
  for x,m in [('buyer',10000000),('seller',10000000),('utility',0),('system_import',0)]:
   self.e.create_company(x,'Уфа',m)
 def tearDown(self):self.e.close()
 def test_contract(self):
  self.e.import_goods('i','seller','AGRI-001',100,10,100)
  self.e.create_contract('c','buyer','seller','AGRI-001',25,20)
  result=self.e.fulfill_contract('c')
  self.assertEqual(result['qty'],25)
  self.assertEqual(self.e.fulfill_contract('c'),result)
  self.assertEqual(self.e.inventory('buyer','AGRI-001'),25)
 def test_facility_ownership(self):
  self.e.create_facility('f','seller','ENT-007',1)
  recipe=next(r for r in self.e.recipes.values() if r['enterprise_id']=='ENT-007')
  with self.assertRaises(ValueError):
   self.e.produce_at('x','buyer','f',recipe['recipe_id'])
 def test_operation_conflict(self):
  self.e.import_goods('i','seller','AGRI-001',100,10,100)
  with self.assertRaises(ValueError):
   self.e.import_goods('i','seller','AGRI-001',50,10,100)
 def test_wages_reach_local_households(self):
  r=next(x for x in self.e.recipes.values() if x["output_goods_id"]=="FOOD-039")
  self.e.create_company("household:Уфа","Уфа",0,"households")
  for i in r["inputs"]:self.e._lot("seller",i["goods_id"],i["quantity"],100)
  before=self.e.total_money()
  self.e.produce("salary","seller",r["recipe_id"])
  self.assertEqual(self.e.balance("household:Уфа"),r["labor_minutes"]*45)
  self.assertEqual(before,self.e.total_money())
 def test_transaction_rolls_back_after_late_error(self):
  self.e.import_goods('i','seller','AGRI-001',100,10,100)
  cash=self.e.balance('buyer')
  # _lot fails after money transfer: DB transaction must rollback
  with self.assertRaises(ValueError):
   self.e.trade('t','buyer','seller','INVALID',1,20)
  self.assertEqual(self.e.balance('buyer'),cash)
if __name__=='__main__':unittest.main()

def test_capacity_and_idempotency(self):
    r=next(r for r in self.e.recipes.values() if r['enterprise_id']=='ENT-007')
    self.e.create_facility('mill','seller','ENT-007',1)
    for i in r['inputs']:
        self.e._lot('seller',i['goods_id'],i['quantity']*3,1000)
    a=self.e.produce_at('p1','seller','mill',r['recipe_id'])
    self.assertEqual(a,self.e.produce_at('p1','seller','mill',r['recipe_id']))
    with self.assertRaises(ValueError):self.e.produce_at('p2','seller','mill',r['recipe_id'])
    self.e.advance(1)
    self.e.produce_at('p2','seller','mill',r['recipe_id'])
BusinessTests.test_capacity_and_idempotency=test_capacity_and_idempotency
