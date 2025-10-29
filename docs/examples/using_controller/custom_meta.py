from http import HTTPStatus
from typing import final

from django.http import HttpResponse

from django_modern_rest import (
    Controller,
    HeaderDescription,
    ResponseDescription,
    validate,
)
from django_modern_rest.plugins.msgspec import MsgspecSerializer


@final
class SettingsController(Controller[MsgspecSerializer]):
    def get(self) -> str:
        return 'default get setting'

    def post(self) -> str:
        return 'default post setting'

    # `meta` response is also validated, schema is required:
    @validate(
        ResponseDescription(
            None,
            status_code=HTTPStatus.NO_CONTENT,
            headers={'Allow': HeaderDescription()},
        ),
    )
    def meta(self) -> HttpResponse:  # Handles `OPTIONS` http method
        return self.to_response(
            None,
            status_code=HTTPStatus.NO_CONTENT,
            headers={
                'Allow': ', '.join(
                    method for method in sorted(self.api_endpoints.keys())
                ),
            },
        )
