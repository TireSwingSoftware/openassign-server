

from collections import Set

from django.core.cache import cache as DEFAULT_CACHE
from django.db.models import signals

import facade

Organization = facade.models.Organization

__all__ = ('ORG_DESCENDANT_CACHE',)

class OrganizationDescendantCache(object):
    """
    A read-only cache that computes and stores a transitive closure over all
    descendants of an Organization. This relationship is determined by the
    `parent` attribute in the `Organization` Model. The cache exposes a
    mapping from organization id to a set of descendant organization ids.

    In other words if A is a parent of B and B is a parent of C, then C is a
    descendant of A. Consequently, a lookup in this cache for the id of A will
    return a set of ids -> {B, C}. A lookup for the id of B will return a
    set -> {C, }. A lookup for the id of C will return an empty set.
    """

    backend = DEFAULT_CACHE  # a Django cache backend
    value_timeout = 2592000 # the backend timeout for stored values

    def __init__(self, backend=None):
        """
        Constructor

        Arguments:
            backend: An optional Django cache backend to use as the backing
                     data store for the cache. If unspecified, the default cache
                     backend is used.
        """
        if backend:
            self.backend = backend

        self.hits = 0 # cache hits
        self.misses = 0 # cache misses

        # seed the generation number
        self.backend.set(self.generation_key, 0, self.value_timeout)

        # connect notifications for organization changes
        signals.post_save.connect(self._post_save, sender=Organization)
        signals.post_delete.connect(self._post_delete, sender=Organization)

    def __del__(self):
        # disconnect organization change notifications
        try:
            # python might be shutting down and these calls will fail
            signals.post_save.disconnect(self._post_save, sender=Organization)
            signals.post_delete.disconnect(self._post_delete, sender=Organization)
        except:
            pass

    #
    # Signal handlers

    def _post_save(self, sender, instance, raw, **kwargs):
        "Post-save Django signal handler."
        if not raw:
            self.rebuild()

    def _post_delete(self, sender, instance, **kwargs):
        "Post-delete Django signal handler."
        self.rebuild()

    @property
    def generation_key(self):
        "A name which distinguishes the entire cache from another cache."
        return type(self).__name__

    @property
    def generation(self):
        "Returns the current cache generation number."
        generation = self.backend.get(self.generation_key)
        if not generation:
            generation = 0
            self.backend.set(self.generation_key, generation)
        return generation

    def _cache_key(self, key, generation=None):
        "Returns a key using the cache name and generation."
        if not generation:
            generation = self.generation
        return '%s:%s:%d' % (self.generation_key, key, generation)

    #
    # Public API

    def rebuild(self, return_key=None):
        """
        Rebuilds the entire cache.

        Arguments:
            return_key: If specified, a cache key indicating the value to
                        return from the newly built cache. This saves an
                        additional backend lookup if you already know the key.
        """
        assert return_key is None or isinstance(return_key, (int, long))

        return_value = None
        next_generation = self.generation + 1

        graph = self._build_org_graph()
        for org_id, node in graph.iteritems():
            # XXX: all new keys are stored in the next generation group
            # which becomes active at the end of this routine
            key = self._cache_key(org_id, next_generation)
            value = frozenset(d.id for d in node.descendants)
            if return_key == org_id:
                assert not return_value
                return_value = value
            self.backend.set(key, value, self.value_timeout)

        self.backend.set(self.generation_key, next_generation)
        return return_value

    #
    # Read-only python mapping API

    def __getitem__(self, key):
        if not isinstance(key, (int, long)):
            raise TypeError("key must be an integer organization id")
        # XXX: read operations will continue to use the current cache
        # generation number while the cache is rebuilt into the next generation.
        value = self.backend.get(self._cache_key(key))
        if value is None or not isinstance(value, Set):
            self.misses += 1
            value = self.rebuild(key)
        else:
            self.hits += 1

        return value

    #
    # Graph construction routines

    def _get_org_nodes(self):
        """
        Builds an adjacency list of organization-parent pairs using
        OrgNode objects. At the end of the routine each node will reference it's
        first order descendants.
        """
        nodes = {}
        for id, parent_id in Organization.objects.values_list('id', 'parent'):
            node = nodes.get(id, None)
            if not node:
                nodes[id] = node = OrgNode(id)
            if parent_id:
                parent = nodes.get(parent_id, None)
                if not parent:
                    parent = OrgNode(parent_id)
                    nodes[parent_id] = parent
                parent.descendants.add(node)
                node.parent = parent
        return nodes

    def _build_org_graph(self):
        """
        Constructs a graph of the transitive closure over
        Organization descendants.

        Returns:
            A dictionary mapping each organization id to an OrgNode object with
            it's descendants' transitive closure computed.
        """
        # Step 1: Convert Organization adjacencies into a Node structure
        # for use in the graph.
        nodes = self._get_org_nodes()

        # Step 2: Build a transitive closure of descendants
        for node in nodes.itervalues():
            if node.parent is None:
                continue
            parent = node.parent.parent
            while parent is not None:
                parent.descendants.add(node)
                parent = parent.parent

        # Return the resulting graph
        return nodes


class OrgNode(object):
    "Internal data structure used in building an Organization graph."

    def __init__(self, id, parent=None, descendants=None):
        self.id = int(id)
        self.parent = parent
        self.descendants = descendants if descendants else set()

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)


ORG_DESCENDANT_CACHE = OrganizationDescendantCache()
