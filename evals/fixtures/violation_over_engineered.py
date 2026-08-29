# expected_layer: 2
# expected_verdict: fail
# rule_id: agent-workflow
class FactoryBuilder:
    def __init__(self):
        self._registry = {}
        self._middleware = []

    def register(self, name, factory):
        self._registry[name] = factory

    def add_middleware(self, mw):
        self._middleware.append(mw)

    def build(self, name, *args, **kwargs):
        for mw in self._middleware:
            mw(name)
        return self._registry[name](*args, **kwargs)


class ServiceLocator:
    def __init__(self):
        self._builder = FactoryBuilder()

    def get(self, name):
        return self._builder.build(name)
