import unittest,tempfile
from pathlib import Path
from core.economy import Economy

class CoreTests(unittest.TestCase):
 def setUp(self):
  self.e=Economy()
  for c,city,money in [('farm','Уфа',500000000),('mill','Уфа',500000000),('bakery','Уфа',500000000),('shop','Уфа',500000000),('customer','Уфа',500000000),('system_import','Уфа',0),('utility','Уфа',0)]:
   self.e.create_company(c,city,money)
 def tearDown(self):self.e.close()
 def test_catalog(self):
  self.assertEqual(len(self.e.goods),300)
  self.assertEqual(len(self.e.recipes),450)
 def test_no_self_import_from_system_account(self):
  with self.assertRaises(ValueError):self.e.import_goods('self','system_import','AGRI-001',10,10,10)
 def test_import_quota(self):
  with self.assertRaises(ValueError):self.e.import_goods('q','farm','AGRI-001',100,10,99)
  self.assertEqual(self.e.inventory('farm','AGRI-001'),0)
 def test_import_idempotent(self):
  a=self.e.import_goods('a','farm','AGRI-001',100000,10,100000)
  b=self.e.import_goods('a','farm','AGRI-001',100000,10,100000)
  self.assertEqual(a,b);self.assertEqual(self.e.inventory('farm','AGRI-001'),100000)
 def test_trade_no_oversell(self):
  self.e.import_goods('i','farm','AGRI-001',100,10,100)
  with self.assertRaises(ValueError):self.e.trade('t','mill','farm','AGRI-001',101,20)
  self.assertEqual(self.e.inventory('farm','AGRI-001'),100)
 def test_trade_atomic_no_cash(self):
  self.e.import_goods('i','farm','AGRI-001',100,10,100)
  self.e.create_company('poor','Уфа',0)
  with self.assertRaises(ValueError):self.e.trade('t','poor','farm','AGRI-001',10,20)
  self.assertEqual(self.e.inventory('farm','AGRI-001'),100)
 def test_trade_money_conserved(self):
  self.e.import_goods('i','farm','AGRI-001',100,10,100)
  before=self.e.total_money()
  self.e.trade('t','mill','farm','AGRI-001',30,20)
  self.assertEqual(before,self.e.total_money())
  self.assertEqual(self.e.inventory('mill','AGRI-001'),30)
  self.assertEqual(self.e.inventory('farm','AGRI-001'),70)
 def test_trade_idempotent(self):
  self.e.import_goods('i','farm','AGRI-001',100,10,100)
  x=self.e.trade('t','mill','farm','AGRI-001',30,20)
  self.assertEqual(x,self.e.trade('t','mill','farm','AGRI-001',30,20))
  self.assertEqual(self.e.inventory('mill','AGRI-001'),30)
 def test_failed_production_atomic(self):
  r=next(iter(self.e.recipes))
  before=self.e.total_money()
  with self.assertRaises(ValueError):self.e.produce('p','farm',r)
  self.assertEqual(before,self.e.total_money())
 def test_production_all_recipes_smoke(self):
  # Test each fixed recipe in a fresh producer with supplied input stocks; no hidden recipes.
  for k,r in self.e.recipes.items():
   with self.subTest(recipe=k):
    e=Economy()
    e.create_company('producer','Уфа',10**13)
    e.create_company('utility','Уфа',0)
    for x in r['inputs']:
     e._lot('producer',x['goods_id'],x['quantity'],x['quantity'])
    before=e.total_money()
    result=e.produce('p','producer',k)
    self.assertEqual(e.inventory('producer',r['output_goods_id']),r['outputs'][0]['quantity'])
    self.assertEqual(before,e.total_money())
    self.assertEqual(result,e.produce('p','producer',k))
    e.close()
 def test_tick(self):
  self.assertEqual(self.e.advance(7),7)
  with self.assertRaises(ValueError):self.e.advance(0)
 def test_negative_rejected(self):
  with self.assertRaises(ValueError):self.e.import_goods('n','farm','AGRI-001',-1,1,5)
  with self.assertRaises(ValueError):self.e.trade('n','mill','farm','AGRI-001',1,-1)
 def test_full_chain(self):
  # Automatically resolve a fixed production chain ending in rye bread, with external primary sources.
  by_output={}
  for r in self.e.recipes.values():
   by_output.setdefault(r['output_goods_id'],r)
  target='FOOD-020';producer='bakery';visited=set()
  def make(sku):
   if sku not in by_output:return
   if sku in visited:return
   r=by_output[sku]
   for i in r['inputs']:make(i['goods_id'])
   # provide raw materials as finite imported stock in the model, with a budget.
   for i in r['inputs']:
    need=i['quantity']
    if self.e.inventory(producer,i['goods_id'])<need:
     diff=need-self.e.inventory(producer,i['goods_id'])
     if self.e.goods[i['goods_id']]['source_mode']!='manufacturing':
      self.e.import_goods('imp-'+sku+'-'+i['goods_id'],producer,i['goods_id'],diff,1,diff)
     else:
      # intermediate might already have been consumed by a sibling recipe; produce more
      make_again(i['goods_id'])
   self.e.produce('prod-'+sku,producer,r['recipe_id'])
   visited.add(sku)
  def make_again(sku):
   visited.discard(sku);make(sku)
  make(target)
  self.assertGreater(self.e.inventory(producer,target),0)

if __name__=='__main__':unittest.main()
