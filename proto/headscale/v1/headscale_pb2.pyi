from google.api import annotations_pb2 as _annotations_pb2
from headscale.v1 import user_pb2 as _user_pb2
from headscale.v1 import preauthkey_pb2 as _preauthkey_pb2
from headscale.v1 import node_pb2 as _node_pb2
from headscale.v1 import apikey_pb2 as _apikey_pb2
from headscale.v1 import auth_pb2 as _auth_pb2
from headscale.v1 import policy_pb2 as _policy_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("database_connectivity",)
    DATABASE_CONNECTIVITY_FIELD_NUMBER: _ClassVar[int]
    database_connectivity: bool
    def __init__(self, database_connectivity: _Optional[bool] = ...) -> None: ...
