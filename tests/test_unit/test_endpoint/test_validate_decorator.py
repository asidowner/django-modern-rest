import json
from http import HTTPMethod, HTTPStatus
from typing import ClassVar, Generic, Literal, TypeVar, final

import pytest
from django.http import HttpResponse
from inline_snapshot import snapshot
from typing_extensions import TypedDict

from django_modern_rest import (
    Blueprint,
    Body,
    Controller,
    HeaderSpec,
    NewHeader,
    ResponseSpec,
    validate,
)
from django_modern_rest.endpoint import Endpoint
from django_modern_rest.exceptions import EndpointMetadataError
from django_modern_rest.plugins.pydantic import (
    PydanticErrorModel,
    PydanticSerializer,
)
from django_modern_rest.test import DMRRequestFactory

_InnerT = TypeVar('_InnerT')


@final
class _CustomResponse(HttpResponse, Generic[_InnerT]):
    """We need to be sure that ``-> _CustomResponse[str]`` also works."""


class _CustomResponseController(Controller[PydanticSerializer]):
    @validate(ResponseSpec(return_type=str, status_code=HTTPStatus.OK))
    def get(self) -> _CustomResponse[str]:
        return _CustomResponse[str](b'"abc"')

    @validate(ResponseSpec(return_type=str, status_code=HTTPStatus.OK))
    def post(self) -> _CustomResponse[_InnerT]:  # pyright: ignore[reportInvalidTypeVarUse]
        return _CustomResponse[_InnerT](b'"abc"')


@pytest.mark.parametrize(
    'method',
    [
        HTTPMethod.GET,
        HTTPMethod.POST,
    ],
)
def test_validate_generic_response_subtype(
    dmr_rf: DMRRequestFactory,
    *,
    method: HTTPMethod,
) -> None:
    """Ensures that response status_code validation works."""
    request = dmr_rf.generic(str(method), '/whatever/')

    response = _CustomResponseController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.OK
    assert isinstance(json.loads(response.content), str)


class _WrongHeadersController(Controller[PydanticSerializer]):
    @validate(
        ResponseSpec(return_type=list[str], status_code=HTTPStatus.OK),
    )
    def get(self) -> HttpResponse:
        """Has extra response headers."""
        return HttpResponse(b'[]', headers={'X-Custom': 'abc'})

    @validate(
        ResponseSpec(
            return_type=list[str],
            status_code=HTTPStatus.OK,
            headers={'X-Custom': HeaderSpec()},
        ),
    )
    def post(self) -> HttpResponse:
        """Has missing described headers."""
        return HttpResponse(b'[]')


@pytest.mark.parametrize(
    'method',
    [
        HTTPMethod.GET,
        HTTPMethod.POST,
    ],
)
def test_validate_wrong_headers(
    dmr_rf: DMRRequestFactory,
    *,
    method: HTTPMethod,
) -> None:
    """Ensures that response headers are validated."""
    request = dmr_rf.generic(str(method), '/whatever/')

    response = _WrongHeadersController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert isinstance(json.loads(response.content)['detail'], str)


class _CorrectHeadersController(Controller[PydanticSerializer]):
    @validate(
        ResponseSpec(
            return_type=list[str],
            status_code=HTTPStatus.OK,
            headers={'X-Custom': HeaderSpec()},
        ),
    )
    def get(self) -> HttpResponse:
        """Has has matching response headers."""
        return HttpResponse(b'[]', headers={'X-Custom': 'abc'})

    @validate(
        ResponseSpec(
            return_type=list[str],
            status_code=HTTPStatus.OK,
            headers={'X-Custom': HeaderSpec(required=False)},
        ),
    )
    def post(self) -> HttpResponse:
        """Has optional header description."""
        return HttpResponse(b'[]')


@pytest.mark.parametrize(
    'method',
    [
        HTTPMethod.GET,
        HTTPMethod.POST,
    ],
)
def test_validate_correct_headers(
    dmr_rf: DMRRequestFactory,
    *,
    method: HTTPMethod,
) -> None:
    """Ensures that response headers are correct."""
    request = dmr_rf.generic(str(method), '/whatever/')

    response = _CorrectHeadersController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == []


class _MismatchingMetadata(Controller[PydanticSerializer]):
    @validate(
        ResponseSpec(int, status_code=HTTPStatus.OK),
    )
    def get(self) -> HttpResponse:
        return 1  # type: ignore[return-value]


def test_validate_over_regular_data(dmr_rf: DMRRequestFactory) -> None:
    """Ensures `@validate` can't mess metadata for raw requests."""
    request = dmr_rf.get('/whatever/')

    response = _MismatchingMetadata.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert '@modify' in json.loads(response.content)['detail']


def test_validate_required_for_responses() -> None:
    """Ensures `@validate` is required for `HttpResponse` returns."""
    with pytest.raises(EndpointMetadataError, match='@validate'):

        class _NoDecorator(Controller[PydanticSerializer]):
            def get(self) -> HttpResponse:
                raise NotImplementedError


class _NoExplicitDecorator(Controller[PydanticSerializer]):
    responses: ClassVar[list[ResponseSpec]] = [
        ResponseSpec(list[int], status_code=HTTPStatus.OK),
    ]

    def get(self) -> HttpResponse:  # valid
        return self.to_response([1, 2])

    def put(self) -> HttpResponse:  # invalid
        return self.to_response(['a'])


def test_no_validate_for_responses(dmr_rf: DMRRequestFactory) -> None:
    """Ensures `@validate` can be skipped, when there are existing responses."""
    request = dmr_rf.get('/whatever/')

    response = _NoExplicitDecorator.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == [1, 2]

    request = dmr_rf.put('/whatever/')

    response = _NoExplicitDecorator.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert json.loads(response.content) == snapshot({
        'detail': [
            {
                'type': 'int_type',
                'loc': [0],
                'msg': 'Input should be a valid integer',
                'input': 'a',
            },
        ],
    })


def test_validate_on_non_response() -> None:
    """Ensures `@validate` can't be used on regular return types."""
    with pytest.raises(EndpointMetadataError, match='@validate'):

        class _WrongValidate(Controller[PydanticSerializer]):
            @validate(  # type: ignore[type-var]
                ResponseSpec(
                    return_type=str,
                    status_code=HTTPStatus.OK,
                ),
            )
            def get(self) -> str:
                raise NotImplementedError


def test_validate_duplicate_statuses() -> None:
    """Ensures `@validate` can't have duplicate status codes."""
    with pytest.raises(EndpointMetadataError, match='different metadata'):

        class _DuplicateStatuses(Controller[PydanticSerializer]):
            @validate(
                ResponseSpec(int, status_code=HTTPStatus.OK),
                ResponseSpec(str, status_code=HTTPStatus.OK),
            )
            async def get(self) -> HttpResponse:
                raise NotImplementedError


def test_validate_raises_on_new_header() -> None:
    """Ensures `@validate` can't be used with `NewHeader`."""
    with pytest.raises(EndpointMetadataError, match='NewHeader'):

        class _WrongValidate(Controller[PydanticSerializer]):
            @validate(
                ResponseSpec(
                    return_type=str,
                    status_code=HTTPStatus.OK,
                    headers={'X-Test': NewHeader(value='Value')},  # type: ignore[dict-item]
                ),
            )
            def get(self) -> HttpResponse:
                raise NotImplementedError


class _EmptyResponseController(Controller[PydanticSerializer]):
    @validate(
        ResponseSpec(
            None,
            status_code=HTTPStatus.NO_CONTENT,
        ),
    )
    def get(self) -> HttpResponse:
        return self.to_response(
            None,
            status_code=HTTPStatus.NO_CONTENT,
        )


def test_validate_empty_response(dmr_rf: DMRRequestFactory) -> None:
    """Ensures `@validate` can validate empty response."""
    request = dmr_rf.get('/whatever/')

    response = _EmptyResponseController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.NO_CONTENT
    assert json.loads(response.content) is None


class _TypedDictResponse(TypedDict):
    user: str


class _TypedDictResponseController(Controller[PydanticSerializer]):
    @validate(
        ResponseSpec(
            _TypedDictResponse,
            status_code=HTTPStatus.OK,
        ),
    )
    def get(self) -> HttpResponse:
        return self.to_response({'user': 'name'})

    @validate(
        ResponseSpec(
            _TypedDictResponse,
            status_code=HTTPStatus.CREATED,
        ),
    )
    def post(self) -> HttpResponse:
        return self.to_response({'user': 1})


def test_validate_type_dict_response(dmr_rf: DMRRequestFactory) -> None:
    """Ensures `@validate` can validate typed dicts."""
    request = dmr_rf.get('/whatever/')
    response = _TypedDictResponseController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == {'user': 'name'}

    request = dmr_rf.post('/whatever/')
    response = _TypedDictResponseController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert json.loads(response.content) == snapshot({
        'detail': [
            {
                'type': 'string_type',
                'loc': ['user'],
                'msg': 'Input should be a valid string',
                'input': 1,
            },
        ],
    })


class _LiteralResponseController(Controller[PydanticSerializer]):
    @validate(
        ResponseSpec(
            Literal[1],
            status_code=HTTPStatus.OK,
        ),
    )
    def get(self) -> HttpResponse:
        return self.to_response(1)

    @validate(
        ResponseSpec(
            Literal[1],
            status_code=HTTPStatus.CREATED,
        ),
    )
    def post(self) -> HttpResponse:
        return self.to_response(2)


def test_validate_literal_response(dmr_rf: DMRRequestFactory) -> None:
    """Ensures `@validate` can validate literals."""
    request = dmr_rf.get('/whatever/')
    response = _LiteralResponseController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.OK
    assert json.loads(response.content) == 1

    request = dmr_rf.post('/whatever/')
    response = _LiteralResponseController.as_view()(request)

    assert isinstance(response, HttpResponse)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert json.loads(response.content) == snapshot({
        'detail': [
            {
                'type': 'literal_error',
                'loc': [],
                'msg': 'Input should be 1',
                'input': 2,
                'ctx': {'expected': '1'},
            },
        ],
    })


def test_validate_sync_error_handler_for_async() -> None:
    """Ensure that it is impossible to pass sync error handler to async case."""
    with pytest.raises(EndpointMetadataError, match=' sync `error_handler`'):

        class _WrongModifyController(Controller[PydanticSerializer]):
            def endpoint_error(
                self,
                endpoint: Endpoint,
                exc: Exception,
            ) -> HttpResponse:
                raise NotImplementedError

            @validate(  # type: ignore[arg-type]
                ResponseSpec(list[int], status_code=HTTPStatus.OK),
                error_handler=endpoint_error,
            )
            async def post(self) -> HttpResponse:
                raise NotImplementedError


def test_validate_async_endpoint_error_for_sync() -> None:
    """Ensure that it is impossible to pass async error handler to sync case."""
    with pytest.raises(EndpointMetadataError, match='async `error_handler`'):

        class _WrongValidateErrorsController(Controller[PydanticSerializer]):
            async def async_endpoint_error(
                self,
                endpoint: Endpoint,
                exc: Exception,
            ) -> HttpResponse:
                raise NotImplementedError

            @validate(  # type: ignore[arg-type]
                ResponseSpec(list[int], status_code=HTTPStatus.OK),
                error_handler=async_endpoint_error,
            )
            def get(self) -> HttpResponse:
                raise NotImplementedError


def test_validate_responses_from_blueprint() -> None:
    """Ensures `@validate` has right `responses` metadata."""

    class _Blueprint(
        Blueprint[PydanticSerializer],
        Body[list[str]],
    ):
        responses: ClassVar[list[ResponseSpec]] = [
            ResponseSpec(
                dict[str, str],
                status_code=HTTPStatus.PAYMENT_REQUIRED,
            ),
        ]

        @validate(
            ResponseSpec(list[int], status_code=HTTPStatus.OK),
        )
        def post(self) -> HttpResponse:
            raise NotImplementedError

    assert _Blueprint.api_endpoints['POST'].metadata.responses == snapshot({
        HTTPStatus.OK: ResponseSpec(
            return_type=list[int],
            status_code=HTTPStatus.OK,
        ),
        HTTPStatus.PAYMENT_REQUIRED: ResponseSpec(
            return_type=dict[str, str],
            status_code=HTTPStatus.PAYMENT_REQUIRED,
        ),
        HTTPStatus.BAD_REQUEST: ResponseSpec(
            return_type=PydanticErrorModel,
            status_code=HTTPStatus.BAD_REQUEST,
        ),
    })


def test_validate_responses_from_components() -> None:
    """Ensures `@validate` has right `responses_from_components` metadata."""

    class _Blueprint(
        Blueprint[PydanticSerializer],
        Body[list[str]],
    ):
        responses_from_components = False
        responses: ClassVar[list[ResponseSpec]] = [
            ResponseSpec(
                dict[str, str],
                status_code=HTTPStatus.PAYMENT_REQUIRED,
            ),
        ]

        @validate(
            ResponseSpec(list[int], status_code=HTTPStatus.OK),
        )
        def post(self) -> HttpResponse:
            raise NotImplementedError

    assert _Blueprint.api_endpoints['POST'].metadata.responses == snapshot({
        HTTPStatus.OK: ResponseSpec(
            return_type=list[int],
            status_code=HTTPStatus.OK,
        ),
        HTTPStatus.PAYMENT_REQUIRED: ResponseSpec(
            return_type=dict[str, str],
            status_code=HTTPStatus.PAYMENT_REQUIRED,
        ),
    })
