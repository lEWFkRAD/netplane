import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from headscale.v1 import preauthkey_pb2 as _preauthkey_pb2
from headscale.v1 import user_pb2 as _user_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RegisterMethod(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    REGISTER_METHOD_UNSPECIFIED: _ClassVar[RegisterMethod]
    REGISTER_METHOD_AUTH_KEY: _ClassVar[RegisterMethod]
    REGISTER_METHOD_CLI: _ClassVar[RegisterMethod]
    REGISTER_METHOD_OIDC: _ClassVar[RegisterMethod]
REGISTER_METHOD_UNSPECIFIED: RegisterMethod
REGISTER_METHOD_AUTH_KEY: RegisterMethod
REGISTER_METHOD_CLI: RegisterMethod
REGISTER_METHOD_OIDC: RegisterMethod

class Node(_message.Message):
    __slots__ = ("id", "machine_key", "node_key", "disco_key", "ip_addresses", "name", "user", "last_seen", "expiry", "pre_auth_key", "created_at", "register_method", "given_name", "online", "approved_routes", "available_routes", "subnet_routes", "tags")
    ID_FIELD_NUMBER: _ClassVar[int]
    MACHINE_KEY_FIELD_NUMBER: _ClassVar[int]
    NODE_KEY_FIELD_NUMBER: _ClassVar[int]
    DISCO_KEY_FIELD_NUMBER: _ClassVar[int]
    IP_ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    EXPIRY_FIELD_NUMBER: _ClassVar[int]
    PRE_AUTH_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    REGISTER_METHOD_FIELD_NUMBER: _ClassVar[int]
    GIVEN_NAME_FIELD_NUMBER: _ClassVar[int]
    ONLINE_FIELD_NUMBER: _ClassVar[int]
    APPROVED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_ROUTES_FIELD_NUMBER: _ClassVar[int]
    SUBNET_ROUTES_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    id: int
    machine_key: str
    node_key: str
    disco_key: str
    ip_addresses: _containers.RepeatedScalarFieldContainer[str]
    name: str
    user: _user_pb2.User
    last_seen: _timestamp_pb2.Timestamp
    expiry: _timestamp_pb2.Timestamp
    pre_auth_key: _preauthkey_pb2.PreAuthKey
    created_at: _timestamp_pb2.Timestamp
    register_method: RegisterMethod
    given_name: str
    online: bool
    approved_routes: _containers.RepeatedScalarFieldContainer[str]
    available_routes: _containers.RepeatedScalarFieldContainer[str]
    subnet_routes: _containers.RepeatedScalarFieldContainer[str]
    tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[int] = ..., machine_key: _Optional[str] = ..., node_key: _Optional[str] = ..., disco_key: _Optional[str] = ..., ip_addresses: _Optional[_Iterable[str]] = ..., name: _Optional[str] = ..., user: _Optional[_Union[_user_pb2.User, _Mapping]] = ..., last_seen: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., expiry: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., pre_auth_key: _Optional[_Union[_preauthkey_pb2.PreAuthKey, _Mapping]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., register_method: _Optional[_Union[RegisterMethod, str]] = ..., given_name: _Optional[str] = ..., online: _Optional[bool] = ..., approved_routes: _Optional[_Iterable[str]] = ..., available_routes: _Optional[_Iterable[str]] = ..., subnet_routes: _Optional[_Iterable[str]] = ..., tags: _Optional[_Iterable[str]] = ...) -> None: ...

class RegisterNodeRequest(_message.Message):
    __slots__ = ("user", "key")
    USER_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    user: str
    key: str
    def __init__(self, user: _Optional[str] = ..., key: _Optional[str] = ...) -> None: ...

class RegisterNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class GetNodeRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    def __init__(self, node_id: _Optional[int] = ...) -> None: ...

class GetNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class SetTagsRequest(_message.Message):
    __slots__ = ("node_id", "tags")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, node_id: _Optional[int] = ..., tags: _Optional[_Iterable[str]] = ...) -> None: ...

class SetTagsResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class SetApprovedRoutesRequest(_message.Message):
    __slots__ = ("node_id", "routes")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    routes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, node_id: _Optional[int] = ..., routes: _Optional[_Iterable[str]] = ...) -> None: ...

class SetApprovedRoutesResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class DeleteNodeRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    def __init__(self, node_id: _Optional[int] = ...) -> None: ...

class DeleteNodeResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ExpireNodeRequest(_message.Message):
    __slots__ = ("node_id", "expiry", "disable_expiry")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    EXPIRY_FIELD_NUMBER: _ClassVar[int]
    DISABLE_EXPIRY_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    expiry: _timestamp_pb2.Timestamp
    disable_expiry: bool
    def __init__(self, node_id: _Optional[int] = ..., expiry: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., disable_expiry: _Optional[bool] = ...) -> None: ...

class ExpireNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class RenameNodeRequest(_message.Message):
    __slots__ = ("node_id", "new_name")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    NEW_NAME_FIELD_NUMBER: _ClassVar[int]
    node_id: int
    new_name: str
    def __init__(self, node_id: _Optional[int] = ..., new_name: _Optional[str] = ...) -> None: ...

class RenameNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class ListNodesRequest(_message.Message):
    __slots__ = ("user",)
    USER_FIELD_NUMBER: _ClassVar[int]
    user: str
    def __init__(self, user: _Optional[str] = ...) -> None: ...

class ListNodesResponse(_message.Message):
    __slots__ = ("nodes",)
    NODES_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[Node]
    def __init__(self, nodes: _Optional[_Iterable[_Union[Node, _Mapping]]] = ...) -> None: ...

class DebugCreateNodeRequest(_message.Message):
    __slots__ = ("user", "key", "name", "routes")
    USER_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    user: str
    key: str
    name: str
    routes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, user: _Optional[str] = ..., key: _Optional[str] = ..., name: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ...) -> None: ...

class DebugCreateNodeResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: Node
    def __init__(self, node: _Optional[_Union[Node, _Mapping]] = ...) -> None: ...

class BackfillNodeIPsRequest(_message.Message):
    __slots__ = ("confirmed",)
    CONFIRMED_FIELD_NUMBER: _ClassVar[int]
    confirmed: bool
    def __init__(self, confirmed: _Optional[bool] = ...) -> None: ...

class BackfillNodeIPsResponse(_message.Message):
    __slots__ = ("changes",)
    CHANGES_FIELD_NUMBER: _ClassVar[int]
    changes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, changes: _Optional[_Iterable[str]] = ...) -> None: ...
