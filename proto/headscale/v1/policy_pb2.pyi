import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SetPolicyRequest(_message.Message):
    __slots__ = ("policy",)
    POLICY_FIELD_NUMBER: _ClassVar[int]
    policy: str
    def __init__(self, policy: _Optional[str] = ...) -> None: ...

class SetPolicyResponse(_message.Message):
    __slots__ = ("policy", "updated_at")
    POLICY_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    policy: str
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, policy: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class GetPolicyRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetPolicyResponse(_message.Message):
    __slots__ = ("policy", "updated_at")
    POLICY_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    policy: str
    updated_at: _timestamp_pb2.Timestamp
    def __init__(self, policy: _Optional[str] = ..., updated_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CheckPolicyRequest(_message.Message):
    __slots__ = ("policy",)
    POLICY_FIELD_NUMBER: _ClassVar[int]
    policy: str
    def __init__(self, policy: _Optional[str] = ...) -> None: ...

class CheckPolicyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
