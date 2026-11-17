import unittest
from core.market import Market
from core.ai import AIManager
class AITests(unittest.TestCase):
 def setUp(self):
  self.e=Market();self.e.create_company("system_import","Уфа",0)
  self.ai=AIManager(self.e,seed=42)
 def tearDown(self):self.e.close()
 def test_bootstrap_100_10_cities(self):
  self.assertEqual(self.ai.bootstrap(100),100)
  self.assertEqual(self.e.db.execute("SELECT COUNT(DISTINCT city) FROM ai_agents").fetchone()[0],10)
  self.assertEqual(self.ai.bootstrap(100),100)
 def test_ai_no_free_goods_or_spending(self):
  self.ai.bootstrap(100)
  initial=self.e.total_money()
  prices={c:200 for c in self.e.goods}
  self.ai.step(prices)
  self.assertEqual(initial,self.e.total_money())
  self.assertEqual(self.e.db.execute("SELECT COUNT(*) FROM ai_decisions").fetchone()[0],100)
  self.assertEqual(sum(self.e.inventory(f"ai-{i:04d}","AGRI-001") for i in range(100)),0)
 def test_repeat_step_idempotent_orders(self):
  self.ai.bootstrap(10)
  prices={c:100 for c in self.e.goods}
  self.ai.step(prices);n=self.e.db.execute("SELECT COUNT(*) FROM market_orders").fetchone()[0]
  self.ai.step(prices)
  self.assertEqual(n,self.e.db.execute("SELECT COUNT(*) FROM market_orders").fetchone()[0])
  self.assertEqual(self.e.db.execute("SELECT COUNT(*) FROM ai_decisions").fetchone()[0],10)
 def test_agents_use_same_cash_constraints(self):
  self.ai.bootstrap(3,initial_cash=100)
  prices={c:10**8 for c in self.e.goods}
  self.ai.step(prices)
  self.assertEqual(self.e.db.execute("SELECT COUNT(*) FROM market_orders").fetchone()[0],0)
if __name__=='__main__':unittest.main()
