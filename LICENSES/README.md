# Third-party source notices

These notices cover the vendored protocol definitions and generated bindings
listed below. They do not assign a license to NetPlane's original plugin code.

## Headscale

- Files: `proto/headscale/v1/*.proto` and their generated Python bindings
  (`*_pb2.py`, `*_pb2.pyi`, `*_pb2_grpc.py`).
- Source: [Headscale v0.29.6, revision a2b1d7863926834e94479dcdd91ab344a9356bd0](https://github.com/juanfont/headscale/tree/a2b1d7863926834e94479dcdd91ab344a9356bd0/proto/headscale/v1).
- Copyright (c) 2020, Juan Font. All rights reserved.
- License: [BSD 3-Clause](HEADSCALE-BSD-3-Clause.txt), copied verbatim from
  [the pinned upstream LICENSE](https://github.com/juanfont/headscale/blob/a2b1d7863926834e94479dcdd91ab344a9356bd0/LICENSE).

## Google APIs

- Files: `proto/google/api/annotations.proto`, `proto/google/api/http.proto`
  and their generated Python bindings (`*_pb2.py`, `*_pb2.pyi`, `*_pb2_grpc.py`).
- Source: [Google APIs, revision dff1cd0c7ff8c26ff4c9f7a87cbe175fb5124d4e](https://github.com/googleapis/googleapis/tree/dff1cd0c7ff8c26ff4c9f7a87cbe175fb5124d4e/google/api).
- `annotations.proto`: Copyright 2025 Google LLC.
- `http.proto`: Copyright 2026 Google LLC.
- License: [Apache License 2.0](GOOGLEAPIS-Apache-2.0.txt), copied verbatim
  from [the pinned upstream LICENSE](https://github.com/googleapis/googleapis/blob/dff1cd0c7ff8c26ff4c9f7a87cbe175fb5124d4e/LICENSE).
  Original copyright and license headers remain in both source files.

The `.proto` sources are unmodified; the bindings are generated using
`grpcio-tools==1.81.1` and `protobuf==6.33.5`. Revision pins, source checksums
and regeneration commands are in [`scripts/gen_proto.sh`](../scripts/gen_proto.sh).
Installed third-party applications and Python runtime dependencies retain
their own licenses; these files are not a replacement for their notices.
