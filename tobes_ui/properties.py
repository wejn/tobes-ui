"""Introspectable and validated properties defined within a class."""
from enum import Enum

class BaseProperty:
    """Base property class, with validation."""
    def __init__(self, *, name=None, type_=None, min_value=None, max_value=None):
        self.name = name
        self.type = type_
        self.min_value = min_value
        self.max_value = max_value

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance._values.get(self.name)

    def __set__(self, instance, value):
        validated = self.validate(value)
        instance._values[self.name] = validated

    def validate(self, value):
        """Validate the attempted set()."""
        if self.type and not isinstance(value, self.type):
            raise TypeError(f"'{self.name}' must be of type {self.type.__name__}")
        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"'{self.name}' must be >= {self.min_value}")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"'{self.name}' must be <= {self.max_value}")
        return value

    def metadata(self):
        """Return metadata about this property."""
        return {
            "name": self.name,
            "type": self.type.__name__ if self.type else None,
            "min": self.min_value,
            "max": self.max_value,
        }


class IntProperty(BaseProperty):
    """Int type property."""
    def __init__(self, **kwargs):
        super().__init__(type_=int, **kwargs)


class FloatProperty(BaseProperty):
    """Float type property."""
    def __init__(self, **kwargs):
        super().__init__(type_=float, **kwargs)

    def validate(self, value):
        """Validate with auto-convert to float."""
        if isinstance(value, int):
            value = float(value)
        return super().validate(value)

class BoolProperty(BaseProperty):
    """Bool type property."""
    def __init__(self, **kwargs):
        super().__init__(type_=bool, **kwargs)


class StringProperty(BaseProperty):
    """String type property."""
    def __init__(self, *, allowed_values=None, **kwargs):
        super().__init__(type_=str, **kwargs)
        self.allowed_values = allowed_values

    def validate(self, value):
        value = super().validate(value)
        if self.allowed_values is not None and value not in self.allowed_values:
            raise ValueError(
                f"'{self.name}' must be one of {self.allowed_values}, got '{value}'"
            )
        return value

    def metadata(self):
        meta = super().metadata()
        meta["allowed_values"] = self.allowed_values
        return meta


class EnumProperty(BaseProperty):
    """Enum type property."""
    def __init__(self, enum_type, **kwargs):
        if not issubclass(enum_type, Enum):
            raise TypeError("EnumProperty requires an Enum type")
        super().__init__(type_=enum_type, **kwargs)
        self.enum_type = enum_type

    def validate(self, value):
        if isinstance(value, str):
            # Allow lookup by name
            try:
                value = self.enum_type[value]
            except KeyError as ex:
                raise ValueError(f"'{value}' is not a valid name in {self.enum_type}") from ex
        elif isinstance(value, self.enum_type):
            pass  # already good
        else:
            raise TypeError(f"'{self.name}' must be an instance of {self.enum_type.__name__}"
                            " or name string")
        return value

    def metadata(self):
        meta = super().metadata()
        meta["enum"] = [e.name for e in self.enum_type]
        return meta


class PropertyMeta(type):
    """Auto-register (collect) all declared BaseProperty instances in clsdef.
    Blows up if any subclass attempts to override an inherited property.
    """
    def __new__(mcs, name, bases, namespace):
        # Collect inherited properties
        inherited_props = {}
        for base in bases:
            if hasattr(base, "_declared_properties"):
                inherited_props.update(base._declared_properties)

        # Collect new properties declared in this class
        new_props = {
            k: v for k, v in namespace.items()
            if isinstance(v, BaseProperty)
        }

        # Check for any name collisions
        for key in new_props:
            if key in inherited_props:
                raise TypeError(
                    f"Property '{key}' in class '{name}' overrides inherited property "
                    f"from base class — overriding is not allowed."
                )

        # Merge inherited + new (new_props take precedence in namespace but we forbid it here)
        all_props = {**inherited_props, **new_props}

        clsobj = super().__new__(mcs, name, bases, namespace)
        clsobj._declared_properties = all_props
        return clsobj


class PropertyContainer(metaclass=PropertyMeta):
    """Base class for a property container. Use to define properties within."""
    def __init__(self, **kwargs):
        # make linter happy
        if not self.__class__._declared_properties:
            self.__class__._declared_properties = {}

        self._values = {}
        for name, _prop in self._declared_properties.items():
            if name in kwargs:
                setattr(self, name, kwargs[name])
            else:
                self._values[name] = None

    def get(self, name):
        """Get the value of the property."""
        if name not in self._declared_properties:
            raise AttributeError(f"Unknown property '{name}'")
        return getattr(self, name)

    def set(self, name, value):
        """Set the value of the property (with validation)."""
        if name not in self._declared_properties:
            raise AttributeError(f"Unknown property '{name}'")
        setattr(self, name, value)

    @classmethod
    def properties(cls):
        """Return a list of properties."""
        return [prop.metadata() for prop in cls._declared_properties.values()]

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)


if __name__ == "__main__":
    from pprint import pprint

    class Mode(Enum):
        """Test enum."""
        OFF = 0
        IDLE = 1
        ACTIVE = 2

    class Config(PropertyContainer):
        """Test property container."""
        temperature = FloatProperty(min_value=-273.15)
        count = IntProperty(min_value=0, max_value=100)
        enabled = BoolProperty()
        name = StringProperty(allowed_values=["foo", "bar", "baz"])
        mode = EnumProperty(Mode)


    cfg = Config(
        temperature=25.5,
        count=10,
        enabled=True,
        name="bar",
        mode="ACTIVE"  # or Mode.ACTIVE
    )

    # Three ways to get
    print(cfg.mode)         # Mode.ACTIVE
    print(cfg.get('mode'))  # Mode.ACTIVE
    print(cfg['mode'])      # Mode.ACTIVE

    # Two ways to set
    print(cfg["count"])     # 10
    cfg.set("count", 99)
    print(cfg.get("count")) # 99
    cfg["count"] = 88
    print(cfg["count"])     # 88
    try:
        cfg["count"] = 'abc'
    except TypeError:
        print("Invalid assign caught... :)")

    print("")

    # Introspection
    pprint(Config.properties())

    print("")

    # Subclassing
    class SubConfig(Config):
        """Subclass of the container."""
        test = BoolProperty()

    pprint([item for item in SubConfig.properties() if item not in Config.properties()])
