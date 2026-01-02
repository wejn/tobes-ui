import pytest
from tobes_ui.common import AttrDict


class TestAttrDict:
    def test_getattr_returns_value(self):
        data = AttrDict({'name': 'Alice', 'age': 30})
        assert data.name == 'Alice'
        assert data.age == 30

    def test_getattr_nested_dict_returns_attrdict(self):
        data = AttrDict({'user': {'name': 'Bob'}})
        user = data.user
        assert isinstance(user, AttrDict)
        assert user.name == 'Bob'

    def test_missing_attribute_raises_attributeerror(self):
        data = AttrDict({'x': 1})
        with pytest.raises(AttributeError) as excinfo:
            _ = data.y
        assert "'AttrDict' object has no attribute 'y'" in str(excinfo.value)

    def test_setattr_creates_new_key(self):
        data = AttrDict()
        data.new_key = 'value'
        assert data['new_key'] == 'value'
        assert data.new_key == 'value'

    def test_setattr_overwrites_existing_key(self):
        data = AttrDict({'key': 'old'})
        data.key = 'new'
        assert data['key'] == 'new'
        assert data.key == 'new'

    def test_nested_access_and_modification(self):
        data = AttrDict({'config': {'debug': False}})
        data.config.debug = True
        assert data['config']['debug'] is True

    def test_regular_dict_behavior_still_works(self):
        data = AttrDict({'a': 1})
        data['b'] = 2
        keys = set(data.keys())
        assert keys == {'a', 'b'}
        assert list(sorted(data.values())) == [1, 2]
        assert 'a' in data

    def test_repr_and_str_do_not_break(self):
        data = AttrDict({'x': 1, 'y': {'z': 2}})
        s = str(data)
        r = repr(data)
        assert 'x' in s
        assert 'y' in r
