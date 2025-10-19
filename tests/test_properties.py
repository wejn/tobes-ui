"""tobes_ui/properties.py tests."""

# pylint: disable=missing-class-docstring, missing-function-docstring

import unittest
from enum import Enum

from tobes_ui.properties import (
    PropertyContainer,
    IntProperty,
    FloatProperty,
    BoolProperty,
    StringProperty,
    EnumProperty,
)

class Mode(Enum):
    OFF = 0
    ON = 1


class BasicConfig(PropertyContainer):
    temp = FloatProperty(min_value=0.0, max_value=100.0)
    count = IntProperty(min_value=0)
    enabled = BoolProperty()
    name = StringProperty(allowed_values=["alpha", "beta"])
    mode = EnumProperty(Mode)


class TestPropertyContainer(unittest.TestCase):

    def test_basic_set_get(self):
        cfg = BasicConfig(temp=25.5, count=3, enabled=True, name="alpha", mode="ON")
        self.assertEqual(cfg.temp, 25.5)
        self.assertEqual(cfg.get("count"), 3)
        self.assertEqual(cfg["enabled"], True)
        self.assertEqual(cfg.mode, Mode.ON)

    def test_invalid_type(self):
        cfg = BasicConfig(temp=20, count=1, enabled=True, name="alpha", mode="OFF")
        with self.assertRaises(TypeError):
            cfg["count"] = "not-an-int"

    def test_bounds_validation(self):
        with self.assertRaises(ValueError):
            BasicConfig(temp=-5, count=1, enabled=True, name="alpha", mode="OFF")

    def test_allowed_string_values(self):
        with self.assertRaises(ValueError):
            BasicConfig(temp=25, count=1, enabled=True, name="gamma", mode="OFF")

    def test_enum_by_name_and_instance(self):
        cfg1 = BasicConfig(temp=20, count=2, enabled=False, name="beta", mode="ON")
        self.assertEqual(cfg1.mode, Mode.ON)

        cfg2 = BasicConfig(temp=20, count=2, enabled=False, name="beta", mode=Mode.ON)
        self.assertEqual(cfg2.mode, Mode.ON)

        with self.assertRaises(ValueError):
            BasicConfig(temp=20, count=2, enabled=False, name="beta", mode="INVALID")

    def test_property_introspection(self):
        props = BasicConfig.properties()
        names = {p["name"] for p in props}
        self.assertSetEqual(
            names, {"temp", "count", "enabled", "name", "mode"}
        )

    def test_inheritance(self):
        class SubConfig(BasicConfig):
            extra = IntProperty(min_value=0)

        cfg = SubConfig(temp=10, count=1, enabled=True, name="alpha", mode="OFF", extra=42)
        self.assertEqual(cfg.extra, 42)
        self.assertEqual(cfg.temp, 10)

    def test_prevent_property_override(self):
        with self.assertRaises(TypeError):
            class BadConfig(BasicConfig): # pylint: disable=unused-variable
                count = IntProperty(min_value=99)  # ❌ Should fail

    def test_default_is_none(self):
        cfg = BasicConfig(temp=25.0, count=1, enabled=True, name="alpha", mode="OFF")
        with self.assertRaises(AttributeError):
            cfg.get("nonexistent")  # should raise, not return None

        class PartialConfig(PropertyContainer):
            a = IntProperty()
            b = IntProperty()

        cfg = PartialConfig(a=1)
        self.assertEqual(cfg.a, 1)
        self.assertIsNone(cfg.b)

    def test_all_get_methods_are_consistent(self):
        cfg = BasicConfig(temp=25.0, count=10, enabled=False, name="beta", mode="OFF")
        for name in ['temp', 'count', 'enabled', 'name', 'mode']:
            self.assertEqual(cfg.get(name), getattr(cfg, name))
            self.assertEqual(cfg.get(name), cfg[name])

    def test_metadata_contents(self):
        meta = BasicConfig.properties()
        names = [m["name"] for m in meta]
        self.assertIn("temp", names)
        temp_meta = next(m for m in meta if m["name"] == "temp")
        self.assertEqual(temp_meta["type"], "float")
        self.assertEqual(temp_meta["min"], 0.0)
        self.assertEqual(temp_meta["max"], 100.0)

    def test_string_property_allowed_values(self):
        with self.assertRaises(ValueError):
            BasicConfig(temp=10, count=1, enabled=True, name="not_allowed", mode="ON")

    def test_enum_property_rejects_non_enum(self):
        with self.assertRaises(TypeError):
            class Bad(PropertyContainer): # pylint: disable=unused-variable
                x = EnumProperty(str)  # Not an Enum subclass

    def test_descriptor_access_from_class(self):
        self.assertIsInstance(BasicConfig.__dict__['count'], IntProperty)

    def test_get_unknown_property_raises(self):
        cfg = BasicConfig(temp=20, count=1, enabled=True, name="alpha", mode="OFF")
        with self.assertRaises(AttributeError):
            cfg.get("not_a_prop")
        with self.assertRaises(AttributeError):
            cfg.set("not_a_prop", 5)

    def test_property_round_trip(self):
        cfg = BasicConfig(temp=30.0, count=3, enabled=False, name="beta", mode="ON")
        for name in BasicConfig._declared_properties: # pylint: disable=protected-access
            value = cfg.get(name)
            cfg.set(name, value)  # should not raise
            self.assertEqual(cfg.get(name), value)

    def test_class_level_override(self):
        class Config(PropertyContainer):
            temperature = FloatProperty(min_value=-273.15, max_value=1000)

        cfg = Config(temperature=25.0)

        # Initial constraints
        self.assertEqual(cfg.temperature, 25.0)
        with self.assertRaises(ValueError):
            cfg.temperature = -300  # below initial min
        with self.assertRaises(ValueError):
            cfg.temperature = 2000  # above initial max

        # Change constraints at the class level
        Config.temperature.min_value = -500
        Config.temperature.max_value = 500

        # Now previously-invalid values are allowed
        cfg.temperature = -300
        self.assertEqual(cfg.temperature, -300)

        cfg.temperature = 499.99
        self.assertEqual(cfg.temperature, 499.99)

        # Still catch values out of the new range
        with self.assertRaises(ValueError):
            cfg.temperature = -600

        with self.assertRaises(ValueError):
            cfg.temperature = 600

if __name__ == "__main__":
    unittest.main(verbosity=2)
