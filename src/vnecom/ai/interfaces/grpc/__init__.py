"""Optional internal gRPC interface; grpc dependencies remain lazy."""


def serve() -> None:
    """P0 placeholder for the retrieval gRPC server."""
    from importlib.util import find_spec

    if find_spec("grpc") is None:
        raise RuntimeError("Install gRPC dependencies with pip install 'vnecom[ai]'")
    raise NotImplementedError("gRPC service is planned for P2")
