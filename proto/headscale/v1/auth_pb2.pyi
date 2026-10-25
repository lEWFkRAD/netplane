from headscale.v1 import node_pb2 as _node_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AuthRegisterRequest(_message.Message):
    __slots__ = ("user", "auth_id")
    USER_FIELD_NUMBER: _ClassVar[int]
    AUTH_ID_FIELD_NUMBER: _ClassVar[int]
    user: str
    auth_id: str
    def __init__(self, user: _Optional[str] = ..., auth_id: _Optional[str] = ...) -> None: ...

class AuthRegisterResponse(_message.Message):
    __slots__ = ("node",)
    NODE_FIELD_NUMBER: _ClassVar[int]
    node: _node_pb2.Node
    def __init__(self, node: _Optional[_Union[_node_pb2.Node, _Mapping]] = ...) -> None: ...

class AuthApproveRequest(_message.Message):
    __slots__ = ("auth_id",)
    AUTH_ID_FIELD_NUMBER: _ClassVar[int]
    auth_id: str
    def __init__(self, auth_id: _Optional[str] = ...) -> None: ...

class AuthApproveResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AuthRejectRequest(_message.Message):
    __slots__ = ("auth_id",)
    AUTH_ID_FIELD_NUMBER: _ClassVar[int]
    auth_id: str
    def __init__(self, auth_id: _Optional[str] = ...) -> None: ...

class AuthRejectResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
