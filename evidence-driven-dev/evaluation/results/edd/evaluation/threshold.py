import sys,unittest
from checks import Route,cases
threshold=float(sys.argv[1]);cases.select_route.__defaults__=(threshold,)
print('實際執行 threshold=',threshold,flush=True)
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Route))
sys.exit(not result.wasSuccessful())
