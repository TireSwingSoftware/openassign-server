from pr_services.base_facade import (
    models,
    managers,
    subsystems,
)

__all__ = ['models', 'managers', 'subsystems']


def import_models(xlocals, xglobals, override=False):
    # this is a hack for now to import all of the models from facade
    updates = {}
    for name in models:
        if not override:
            assert not (xlocals and name in xlocals)
            assert not (xglobals and name in xglobals)
        model = getattr(models, name)
        updates[name] = model
    if xlocals:
        xlocals.update(updates)
    if xglobals:
        xglobals.update(updates)
