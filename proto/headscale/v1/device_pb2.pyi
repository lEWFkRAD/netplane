import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Latency(_message.Message):
    __slots__ = ("latency_ms", "preferred")
    LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    PREFERRED_FIELD_NUMBER: _ClassVar[int]
    latency_ms: float
    preferred: bool
    def __init__(self, latency_ms: _Optional[float] = ..., preferred: _Optional[bool] = ...) -> None: ...

class ClientSupports(_message.Message):
    __slots__ = ("hair_pinning", "ipv6", "pcp", "pmp", "udp", "upnp")
    HAIR_PINNING_FIELD_NUMBER: _ClassVar[int]
    IPV6_FIELD_NUMBER: _ClassVar[int]
    PCP_FIELD_NUMBER: _ClassVar[int]
    PMP_FIELD_NUMBER: _ClassVar[int]
    UDP_FIELD_NUMBER: _ClassVar[int]
    UPNP_FIELD_NUMBER: _ClassVar[int]
    hair_pinning: bool
    ipv6: bool
    pcp: bool
    pmp: bool
    udp: bool
    upnp: bool
    def __init__(self, hair_pinning: _Optional[bool] = ..., ipv6: _Optional[bool] = ..., pcp: _Optional[bool] = ..., pmp: _Optional[bool] = ..., udp: _Optional[bool] = ..., upnp: _Optional[bool] = ...) -> None: ...

class ClientConnectivity(_message.Message):
    __slots__ = ("endpoints", "derp", "mapping_varies_by_dest_ip", "latency", "client_supports")
    class LatencyEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Latency
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Latency, _Mapping]] = ...) -> None: ...
    ENDPOINTS_FIELD_NUMBER: _ClassVar[int]
    DERP_FIELD_NUMBER: _ClassVar[int]
    MAPPING_VARIES_BY_DEST_IP_FIELD_NUMBER: _ClassVar[int]
    LATENCY_FIELD_NUMBER: _ClassVar[int]
    CLIENT_SUPPORTS_FIELD_NUMBER: _ClassVar[int]
    endpoints: _containers.RepeatedScalarFieldContainer[str]
    derp: str
    mapping_varies_by_dest_ip: bool
    latency: _containers.MessageMap[str, Latency]
    client_supports: ClientSupports
    def __init__(self, endpoints: _Optional[_Iterable[str]] = ..., derp: _Optional[str] = ..., mapping_varies_by_dest_ip: _Optional[bool] = ..., latency: _Optional[_Mapping[str, Latency]] = ..., client_supports: _Optional[_Union[ClientSupports, _Mapping]] = ...) -> None: ...

class GetDeviceRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class GetDeviceResponse(_message.Message):
    __slots__ = ("addresses", "id", "user", "name", "hostname", "client_version", "update_available", "os", "created", "last_seen", "key_expiry_disabled", "expires", "authorized", "is_external", "machine_key", "node_key", "blocks_incoming_connections", "enabled_routes", "advertised_routes", "client_connectivity")
    ADDRESSES_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    USER_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    HOSTNAME_FIELD_NUMBER: _ClassVar[int]
    CLIENT_VERSION_FIELD_NUMBER: _ClassVar[int]
    UPDATE_AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    OS_FIELD_NUMBER: _ClassVar[int]
    CREATED_FIELD_NUMBER: _ClassVar[int]
    LAST_SEEN_FIELD_NUMBER: _ClassVar[int]
    KEY_EXPIRY_DISABLED_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_FIELD_NUMBER: _ClassVar[int]
    AUTHORIZED_FIELD_NUMBER: _ClassVar[int]
    IS_EXTERNAL_FIELD_NUMBER: _ClassVar[int]
    MACHINE_KEY_FIELD_NUMBER: _ClassVar[int]
    NODE_KEY_FIELD_NUMBER: _ClassVar[int]
    BLOCKS_INCOMING_CONNECTIONS_FIELD_NUMBER: _ClassVar[int]
    ENABLED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    ADVERTISED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    CLIENT_CONNECTIVITY_FIELD_NUMBER: _ClassVar[int]
    addresses: _containers.RepeatedScalarFieldContainer[str]
    id: str
    user: str
    name: str
    hostname: str
    client_version: str
    update_available: bool
    os: str
    created: _timestamp_pb2.Timestamp
    last_seen: _timestamp_pb2.Timestamp
    key_expiry_disabled: bool
    expires: _timestamp_pb2.Timestamp
    authorized: bool
    is_external: bool
    machine_key: str
    node_key: str
    blocks_incoming_connections: bool
    enabled_routes: _containers.RepeatedScalarFieldContainer[str]
    advertised_routes: _containers.RepeatedScalarFieldContainer[str]
    client_connectivity: ClientConnectivity
    def __init__(self, addresses: _Optional[_Iterable[str]] = ..., id: _Optional[str] = ..., user: _Optional[str] = ..., name: _Optional[str] = ..., hostname: _Optional[str] = ..., client_version: _Optional[str] = ..., update_available: _Optional[bool] = ..., os: _Optional[str] = ..., created: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_seen: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., key_expiry_disabled: _Optional[bool] = ..., expires: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., authorized: _Optional[bool] = ..., is_external: _Optional[bool] = ..., machine_key: _Optional[str] = ..., node_key: _Optional[str] = ..., blocks_incoming_connections: _Optional[bool] = ..., enabled_routes: _Optional[_Iterable[str]] = ..., advertised_routes: _Optional[_Iterable[str]] = ..., client_connectivity: _Optional[_Union[ClientConnectivity, _Mapping]] = ...) -> None: ...

class DeleteDeviceRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class DeleteDeviceResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetDeviceRoutesRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class GetDeviceRoutesResponse(_message.Message):
    __slots__ = ("enabled_routes", "advertised_routes")
    ENABLED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    ADVERTISED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    enabled_routes: _containers.RepeatedScalarFieldContainer[str]
    advertised_routes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, enabled_routes: _Optional[_Iterable[str]] = ..., advertised_routes: _Optional[_Iterable[str]] = ...) -> None: ...

class EnableDeviceRoutesRequest(_message.Message):
    __slots__ = ("id", "routes")
    ID_FIELD_NUMBER: _ClassVar[int]
    ROUTES_FIELD_NUMBER: _ClassVar[int]
    id: str
    routes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[str] = ..., routes: _Optional[_Iterable[str]] = ...) -> None: ...

class EnableDeviceRoutesResponse(_message.Message):
    __slots__ = ("enabled_routes", "advertised_routes")
    ENABLED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    ADVERTISED_ROUTES_FIELD_NUMBER: _ClassVar[int]
    enabled_routes: _containers.RepeatedScalarFieldContainer[str]
    advertised_routes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, enabled_routes: _Optional[_Iterable[str]] = ..., advertised_routes: _Optional[_Iterable[str]] = ...) -> None: ...
