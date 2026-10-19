"""Frozen self-authored synthetic engineering tasks and independent tests.

Only description/contract are sent to native models; only description to Jev.
Reference and test source strings execute exclusively in the isolated grader.
"""

TASKS = (
    {
        "id": "normalize-tags",
        "description": "Implement a small Python function that normalizes comma-separated tags with whitespace trimming, Unicode case folding, stable deduplication, empty-token removal and explicit input type validation.",
        "contract": "Implement normalize_tags(text). Require str, otherwise raise TypeError (including bool). Split on commas, strip surrounding whitespace, casefold each token, omit empty tokens, deduplicate while preserving first occurrence. Return a list of strings. Standard library only.",
        "reference": '''def normalize_tags(text):
    if not isinstance(text, str):
        raise TypeError()
    result = []
    seen = set()
    for token in text.split(','):
        token = token.strip().casefold()
        if token and token not in seen:
            result.append(token)
            seen.add(token)
    return result
''',
        "broken": "def normalize_tags(text): return sorted(set(text.lower().split(',')))\n",
        "tests": '''import random, unittest
from solution import normalize_tags
class Tags(unittest.TestCase):
 def test_basic_and_order(self):
  self.assertEqual(normalize_tags(' Foo ,BAR,foo,, baz '), ['foo','bar','baz'])
  self.assertEqual(normalize_tags('z,a,z,b,a'), ['z','a','b'])
 def test_empty(self):
  for value in ('', ' , , ', '\\t,\\n'):
   self.assertEqual(normalize_tags(value), [])
 def test_unicode(self):
  self.assertEqual(normalize_tags('Straße,STRASSE,Ä,ä'), ['strasse','ä'])
 def test_types(self):
  for value in (None, [], 3, True, b'a,b'):
   with self.assertRaises(TypeError): normalize_tags(value)
 def test_seeded_cases(self):
  rng=random.Random(19)
  tokens=[' a ', 'B', '', 'a', 'Straße', 'STRASSE', ' c']
  for _ in range(200):
   chosen=[rng.choice(tokens) for _ in range(rng.randrange(20))]
   expected=[]
   for raw in chosen:
    normal=raw.strip().casefold()
    if normal and normal not in expected: expected.append(normal)
   self.assertEqual(normalize_tags(','.join(chosen)), expected)
''',
    },
    {
        "id": "merge-ranges",
        "description": "Implement deterministic merging of closed integer intervals in Python, handling unsorted overlapping and contained ranges without changing caller data. Validate malformed bounds and distinguish shared endpoints from adjacent disjoint ranges.",
        "contract": "Implement merge_ranges(ranges). Input is a list/tuple of list/tuple pairs [start,end], with exact int bounds (bool disallowed), start<=end. Raise ValueError for every malformed input. Return sorted merged intervals as lists. Merge only overlapping intervals, including shared endpoints; [1,2] and [3,4] remain separate. Preserve caller input, including on failure. Empty input returns []. Standard library only.",
        "reference": '''def merge_ranges(ranges):
    if not isinstance(ranges, (list, tuple)):
        raise ValueError()
    checked=[]
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair)!=2:
            raise ValueError()
        a,b=pair
        if type(a) is not int or type(b) is not int or a>b:
            raise ValueError()
        checked.append((a,b))
    result=[]
    for a,b in sorted(checked):
        if result and a<=result[-1][1]:
            result[-1][1]=max(result[-1][1],b)
        else:
            result.append([a,b])
    return result
''',
        "broken": "def merge_ranges(ranges): return [list(x) for x in sorted(ranges)]\n",
        "tests": '''import copy, random, unittest
from solution import merge_ranges
class Ranges(unittest.TestCase):
 def test_overlap_containment_and_points(self):
  self.assertEqual(merge_ranges([[5,8],[1,3],[2,6],[8,8]]), [[1,8]])
  self.assertEqual(merge_ranges([[2,2],[1,1],[2,3],[1,2]]), [[1,3]])
 def test_adjacency_is_not_overlap(self):
  self.assertEqual(merge_ranges([[3,4],[1,2]]), [[1,2],[3,4]])
  self.assertEqual(merge_ranges([[-4,-2],[-2,0],[1,1]]), [[-4,0],[1,1]])
 def test_empty_tuple_and_immutability(self):
  self.assertEqual(merge_ranges(()), [])
  self.assertEqual(merge_ranges(((3,4),(1,2))), [[1,2],[3,4]])
  value=[[3,5],[1,4]]; before=copy.deepcopy(value)
  self.assertEqual(merge_ranges(value), [[1,5]]); self.assertEqual(value,before)
 def test_invalid_atomic(self):
  cases=[None, '12', [1], [[1]], [[1,2,3]], [[2,1]], [[True,3]], [[1,2.0]], [[0,2],['a',3]]]
  for value in cases:
   before=copy.deepcopy(value)
   with self.assertRaises(ValueError): merge_ranges(value)
   self.assertEqual(value,before)
 def test_seeded_invariants(self):
  rng=random.Random(47)
  for _ in range(100):
   pairs=[sorted([rng.randrange(-8,9),rng.randrange(-8,9)]) for _ in range(rng.randrange(10))]
   before=copy.deepcopy(pairs); result=merge_ranges(pairs)
   self.assertEqual(pairs,before)
   self.assertEqual(result,sorted(result))
   for a,b in result: self.assertLessEqual(a,b)
   for left,right in zip(result,result[1:]): self.assertLess(left[1],right[0])
   # Half-integer samples distinguish closed overlap from integer adjacency.
   for twice in range(-18,19):
    self.assertEqual(any(2*a<=twice<=2*b for a,b in pairs),any(2*a<=twice<=2*b for a,b in result))
''',
    },
    {
        "id": "dependency-batches",
        "description": "Implement topological scheduling batches for a Python dependency graph. Produce deterministic lexicographic maximal ready layers, reject cycles and missing dependencies, deduplicate edges and preserve caller data.",
        "contract": "Implement topological_batches(dependencies). Require a dict mapping nonempty str node names to list/tuple of nonempty str prerequisite names, all present as keys. Raise ValueError for malformed input, missing references or cycles (including self edges). Repeated prerequisites count once. Each output batch contains ALL currently ready nodes, lexicographically sorted; prerequisites must appear in earlier batches. Return list of batches, [] for empty graph. Do not mutate input. Standard library only.",
        "reference": '''def topological_batches(dependencies):
    if not isinstance(dependencies,dict): raise ValueError()
    nodes=set(dependencies)
    if any(not isinstance(n,str) or not n for n in nodes): raise ValueError()
    pending={}
    for node,parents in dependencies.items():
        if not isinstance(parents,(list,tuple)) or any(not isinstance(p,str) or not p or p not in nodes for p in parents):
            raise ValueError()
        pending[node]=set(parents)
    result=[]
    while pending:
        ready=sorted(n for n,parents in pending.items() if not parents)
        if not ready: raise ValueError()
        result.append(ready)
        for n in ready: del pending[n]
        for parents in pending.values(): parents.difference_update(ready)
    return result
''',
        "broken": "def topological_batches(dependencies): return [sorted(dependencies)] if dependencies else []\n",
        "tests": '''import copy, random, unittest
from solution import topological_batches
class Dependencies(unittest.TestCase):
 def test_maximal_sorted_batches(self):
  graph={'finish':['left','right'],'right':['start'],'left':['start'],'start':[], 'alone':[]}
  self.assertEqual(topological_batches(graph), [['alone','start'],['left','right'],['finish']])
 def test_duplicates_empty_and_immutability(self):
  self.assertEqual(topological_batches({}), [])
  graph={'b':['a','a'],'a':[]}; before=copy.deepcopy(graph)
  self.assertEqual(topological_batches(graph), [['a'],['b']]); self.assertEqual(graph,before)
 def test_cycles_and_missing(self):
  for graph in ({'a':['a']},{'a':['b'],'b':['a']},{'a':['missing']},{'a':[],'b':['c'],'c':['b']}):
   before=copy.deepcopy(graph)
   with self.assertRaises(ValueError): topological_batches(graph)
   self.assertEqual(graph,before)
 def test_bad_types(self):
  for graph in ([], None, {'':[]}, {1:[]}, {'a':'a'}, {'a':[3]}, {'a':[None]}, {'a':set()}):
   with self.assertRaises(ValueError): topological_batches(graph)
 def test_seeded_dags(self):
  rng=random.Random(81)
  for _ in range(100):
   names=list('abcdefgh')[:rng.randrange(1,9)]
   graph={n:[p for p in names[:i] if rng.random()<.4] for i,n in enumerate(names)}
   before=copy.deepcopy(graph); layers=topological_batches(graph)
   self.assertEqual(graph,before)
   pending=set(graph); completed=set()
   for layer in layers:
    expected=sorted(n for n in pending if set(graph[n])<=completed)
    self.assertEqual(layer,expected); pending.difference_update(layer); completed.update(layer)
   self.assertFalse(pending)
''',
    },
)
