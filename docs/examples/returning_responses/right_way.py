from http import HTTPStatus
from typing import final

import msgspec

from django_modern_rest import (
    APIError,
    Body,
    Controller,
    Headers,
    ResponseDescription,
    modify,
)
from django_modern_rest.plugins.msgspec import MsgspecSerializer


class UserModel(msgspec.Struct):
    email: str


class HeaderModel(msgspec.Struct):
    consumer: str = msgspec.field(name='X-API-Consumer')


@final
class UserController(
    Controller[MsgspecSerializer],
    Body[UserModel],
    Headers[HeaderModel],
):
    @modify(
        extra_responses=[
            ResponseDescription(
                dict[str, str],
                status_code=HTTPStatus.NOT_ACCEPTABLE,
            ),
        ],
    )
    def post(self) -> UserModel:
        if self.parsed_headers.consumer != 'my-api':
            # Notice that this response is now documented in the spec,
            # no error will happen, no need to disable the validation.
            raise APIError(
                {'detail': 'Wrong API consumer'},
                status_code=HTTPStatus.NOT_ACCEPTABLE,
            )
        # This response will be documented by default:
        return self.parsed_body
