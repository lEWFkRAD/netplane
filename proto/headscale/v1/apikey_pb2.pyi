import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ApiKey(_message.Message):
    __slots__ = ("id", "prefix", "expiration", "created_at", "last_seen")
    ID_FIELD_NUMBER: _ClassVar[int]
    PREFIX_FIELD_NUMBER: _ClassVar[int]
    EXPIRATION_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    id: int
    prefix: str
    expiration: _timestamp_pb2.Timestamp
    created_at: _timestamp_pb2.Timestamp
    last_seen: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., prefix: _Optional[str] = ..., expiration: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_seen: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateApiKeyRequest(_message.Message):
    __slots__ = ("expiration",)
    EXPIRATION_FIELD_NUMBER: _ClassVar[int]
    expiration: _timestamp_pb2.Timestamp
    def __init__(self, expiration: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class CreateApiKeyResponse(_message.Message):
    __slots__ = ("api_key",)
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    api_key: str
    def __init__(self, api_key: _Optional[str] = ...) -> None: ...

class ExpireApiKeyRequest(_message.Message):
    __slots__ = ("prefix", "id")
    PREFIX_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    prefix: str
    id: int
    def __init__(self, prefix: _Optional[str] = ..., id: _Optional[int] = ...) -> None: ...

class ExpireApiKeyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListApiKeysRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListApiKeysResponse(_message.Message):
    __slots__ = ("api_keys",)
    API_KEYS_FIELD_NUMBER: _ClassVar[int]
    api_keys: _containers.RepeatedCompositeFieldContainer[ApiKey]
    def __init__(self, api_keys: _Optional[_Iterable[_Union[ApiKey, _Mapping]]] = ...) -> None: ...

class DeleteApiKeyRequest(_message.Message):
    __slots__ = ("prefix", "id")
    PREFIX_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    prefix: str
    id: int
    def __init__(self, prefix: _Optional[str] = ..., id: _Optional[int] = ...) -> None: ...

class DeleteApiKeyResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
