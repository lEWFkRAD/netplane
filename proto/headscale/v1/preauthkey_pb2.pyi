import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from headscale.v1 import user_pb2 as _user_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PreAuthKey(_message.Message):
    __slots__ = ("user", "id", "key", "reusable", "ephemeral", "used", "expiration", "created_at", "acl_tags")
    USER_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    REUSABLE_FIELD_NUMBER: _ClassVar[int]
    EPHEMERAL_FIELD_NUMBER: _ClassVar[int]
    USED_FIELD_NUMBER: _ClassVar[int]
    EXPIRATION_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ACL_TAGS_FIELD_NUMBER: _ClassVar[int]
    user: _user_pb2.User
    id: int
    key: str
    reusable: bool
    ephemeral: bool
    used: bool
    expiration: _timestamp_pb2.Timestamp
    created_at: _timestamp_pb2.Timestamp
    acl_tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, user: _Optional[_Union[_user_pb2.User, _Mapping]] = ..., id: _Optional[int] = ..., key: _Optional[str] = ..., reusable: _Optional[bool] = ..., ephemeral: _Optional[bool] = ..., used: _Optional[bool] = ..., expiration: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., acl_tags: _Optional[_Iterable[str]] = ...) -> None: ...

class CreatePreAuthKeyRequest(_message.Message):
    __slots__ = ("user", "reusable", "ephemeral", "expiration", "acl_tags")
    USER_FIELD_NUMBER: _ClassVar[int]
    REUSABLE_FIELD_NUMBER: _ClassVar[int]
    EPHEMERAL_FIELD_NUMBER: _ClassVar[int]
    EXPIRATION_FIELD_NUMBER: _ClassVar[int]
    ACL_TAGS_FIELD_NUMBER: _ClassVar[int]
    user: int
    reusable: bool
    ephemeral: bool
    expiration: _timestamp_pb2.Timestamp
    acl_tags: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, user: _Optional[int] = ..., reusable: _Optional[bool] = ..., ephemeral: _Optional[bool] = ..., expiration: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., acl_tags: _Optional[_Iterable[str]] = ...) -> None: ...

class CreatePreAuthKeyResponse(_message.Message):
    __slots__ = ("pre_auth_key",)
    PRE_AUTH_KEY_FIELD_NUMBER: _ClassVar[int]
    pre_auth_key: PreAuthKey
    def __init__(self, pre_auth_key: _Optional[_Union[PreAuthKey, _Mapping]] = ...) -> None: ...

class ExpirePreAuthKeyRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class ExpirePreAuthKeyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class DeletePreAuthKeyRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class DeletePreAuthKeyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListPreAuthKeysRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListPreAuthKeysResponse(_message.Message):
    __slots__ = ("pre_auth_keys",)
    PRE_AUTH_KEYS_FIELD_NUMBER: _ClassVar[int]
    pre_auth_keys: _containers.RepeatedCompositeFieldContainer[PreAuthKey]
    def __init__(self, pre_auth_keys: _Optional[_Iterable[_Union[PreAuthKey, _Mapping]]] = ...) -> None: ...
