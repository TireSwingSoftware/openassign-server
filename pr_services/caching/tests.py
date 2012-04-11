
from random import randint
from mock import Mock, MagicMock

from pr_services.caching import OrganizationDescendentCache
from pr_services.testlib import TestCase

import facade

Organization = facade.models.Organization

class TestOrgDescendentCache(TestCase):
    fixtures = ['precor_orgs']

    class MockCacheBackend(dict):
        def get(self, key, default=None):
            try:
                return self[key]
            except KeyError:
                return default

        def set(self, key, value, timeout=None):
            self[key] = value

        def delete(self, key):
            try:
                del self[key]
            except KeyError:
                pass

    def setUp(self):
        super(TestOrgDescendentCache, self).setUp()
        _backend = self.MockCacheBackend()
        self.backend = MagicMock(wraps=_backend)
        self.cache = OrganizationDescendentCache(backend=self.backend)
        self.cache.rebuild = Mock(wraps=self.cache.rebuild)
        self.expected = { # based on the precor_orgs fixture
            1: frozenset((2,3,4,5,6,7)),
            2: frozenset((4,5)),
            3: frozenset((6,7)),
            4: frozenset(),
            5: frozenset(),
            6: frozenset(),
            7: frozenset(),
            8: frozenset((9, 10)),
            9: frozenset(),
           10: frozenset()
        }

    def test_get(self):
        v = self.expected[1]
        self.assertEquals(self.cache.rebuild.call_count, 0)
        self.assertEquals(self.cache[1], v)
        self.assertEquals(self.cache.misses, 1)
        self.assertEquals(self.cache.hits, 0)
        self.assertEquals(self.cache.rebuild.call_count, 1)

        self.assertEquals(self.cache[1], v)
        self.assertEquals(self.cache.misses, 1)
        self.assertEquals(self.cache.hits, 1)
        self.assertEquals(self.cache.rebuild.call_count, 1)

        self.assertEquals(self.cache[1L], v)
        self.assertEquals(self.cache.misses, 1)
        self.assertEquals(self.cache.hits, 2)
        self.assertEquals(self.cache.rebuild.call_count, 1)

        self.assertEquals(self.cache[1000000], None)
        self.assertEquals(self.cache.misses, 2)
        self.assertEquals(self.cache.hits, 2)
        self.assertEquals(self.cache.rebuild.call_count, 2)

    def test_bad_args(self):
        with self.assertRaises(TypeError):
            self.cache[None]
        with self.assertRaises(TypeError):
            self.cache['asdf']
        with self.assertRaises(TypeError):
            self.cache[3.5]

    def test_rebuild(self):
        self.assertEquals(self.cache.rebuild(1), self.expected[1])
        self.assertEquals(self.cache.rebuild(100000), None)

    def test_flakey_backend(self):
        def broken_setter(*args, **kw):
            return
        self.backend.set = broken_setter
        v = self.expected[1]
        self.assertEquals(self.cache.rebuild(1), v)
        self.assertEquals(self.cache[1], v)
        self.assertEquals(self.cache.rebuild(500), None)
        self.assertEquals(self.cache[500], None)

        def broken_getter(*args, **kw):
            return
        self.backend.get = broken_getter
        self.assertEquals(self.cache.rebuild(1), v)
        self.assertEquals(self.cache[1], v)
        self.assertEquals(self.cache.rebuild(500), None)
        self.assertEquals(self.cache[500], None)

    def test_heavy_contention(self):
        genkey = self.cache.generation_key
        def incr_gen(*args, **kw):
            gen = self.backend[genkey]
            self.backend[genkey] += randint(1,4)
        self.backend.set.side_effect = incr_gen
        self.backend.get.side_effect = incr_gen

        self.cache.rebuild()
        for key, value in self.expected.iteritems():
            self.assertEquals(self.cache[key], value)
        self.cache.rebuild()
        self.cache.rebuild()
        for key, value in self.expected.iteritems():
            self.assertEquals(self.cache[key], value)

    def test_dropped_keys(self):
        self.cache.rebuild()
        self.assertEquals(self.cache._cache_key(1),
                'OrganizationDescendentCache:1:1')
        self.assertEquals(self.cache.generation, 1)
        self.assertEquals(self.cache[1], self.expected[1])
        self.assertEquals(self.cache.hits, 1)
        self.assertEquals(self.cache.misses, 0)
        self.backend.clear()
        self.backend.set(self.cache.generation_key, 1)
        self.assertEquals(self.cache[1], self.expected[1])
        self.assertEquals(self.cache._cache_key(1),
                'OrganizationDescendentCache:1:2')
        self.assertEquals(self.cache.generation, 2)
        self.assertEquals(self.cache.hits, 1)
        self.assertEquals(self.cache.misses, 1)

    def test_key_generation(self):
        one = self.cache._cache_key('foo')
        self.assertEquals(one, 'OrganizationDescendentCache:foo:0')

        self.cache.rebuild()
        two = self.cache._cache_key('foo')
        self.assertEquals(two, 'OrganizationDescendentCache:foo:1')

        self.cache.rebuild()
        three = self.cache._cache_key('foo')
        self.assertEquals(three, 'OrganizationDescendentCache:foo:2')

    def test_descendents(self):
        for key, value in self.expected.iteritems():
            self.assertEquals(self.cache[key], value)

    def test_many_descendents(self):
        org = prev = Organization.objects.create(name='Foo')
        expected = set()
        for i in range(20):
            prev = Organization.objects.create(parent=prev, name='Foo %d' % i)
            expected.add(prev.id)

        self.assertEquals(self.cache[org.id], expected)

    def test_delete_org(self):
        self.assertEquals(self.cache[1], self.expected[1])
        self.assertEquals(self.cache[2], self.expected[2])
        org_4_5 = Organization.objects.filter(id__in=[4,5])
        org_4_5.delete()
        self.assertEquals(self.cache[1], frozenset((2,3,6,7)))
        self.assertEquals(self.cache[2], frozenset())
        self.assertEquals(self.cache[4], None)
        self.assertEquals(self.cache[5], None)

    def test_modify_org(self):
        self.assertEquals(self.cache[1], self.expected[1])
        self.assertEquals(self.cache[2], self.expected[2])
        org4 = Organization.objects.get(id=4)
        org4.parent = None
        org4.save()
        org5 = Organization.objects.get(id=5)
        org5.parent = None
        org5.save()
        self.assertEquals(self.cache[1], frozenset((2,3,6,7)))
        self.assertEquals(self.cache[2], frozenset())
        self.assertEquals(self.cache[4], frozenset())
        self.assertEquals(self.cache[5], frozenset())
