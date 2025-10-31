from http import HTTPStatus
from typing import final

import pydantic
from django.http import HttpResponse

from django_modern_rest import (
    Body,
    Controller,
    ResponseSpec,
    validate,
)
from django_modern_rest.plugins.pydantic import PydanticSerializer


class UserModel(pydantic.BaseModel):
    email: str


@final
class UserController(
    Controller[PydanticSerializer],
    Body[UserModel],
):
    @validate(  # <- describes unique return types from this endpoint
        ResponseSpec(
            UserModel,
            status_code=HTTPStatus.OK,
        ),
    )
    def post(self) -> HttpResponse:
        # This response would have an explicit status code `200`:
        return self.to_response(
            self.parsed_body,
            status_code=HTTPStatus.OK,
        )
