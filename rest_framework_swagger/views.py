import json
from django.utils import six

from django.views.generic import View
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_text
from django.shortcuts import render_to_response, RequestContext
from django.core.exceptions import PermissionDenied
from .compat import import_string

from rest_framework.views import Response
from rest_framework.settings import api_settings
from rest_framework.utils import formatting

from rest_framework_swagger.urlparser import UrlParser
from rest_framework_swagger.apidocview import APIDocView
from rest_framework_swagger.docgenerator import DocumentationGenerator

from rest_framework_swagger import SWAGGER_SETTINGS


try:
    JSONRenderer = list(filter(
        lambda item: item.format == 'json',
        api_settings.DEFAULT_RENDERER_CLASSES,
    ))[0]
except IndexError:
    from rest_framework.renderers import JSONRenderer


def get_restructuredtext(view_cls, html=False):
    from docutils import core

    description = view_cls.__doc__ or ''
    description = formatting.dedent(smart_text(description))
    if html:
        parts = core.publish_parts(source=description, writer_name='html')
        html = parts['body_pre_docinfo'] + parts['fragment']
        return mark_safe(html)
    return description


def get_full_base_path(request):
    protocol = SWAGGER_SETTINGS.get('protocol', 'http')
    if 'base_path' in SWAGGER_SETTINGS:
        return ("%s://%s" % (protocol, SWAGGER_SETTINGS.get('base_path', '').rstrip('/'))).rstrip('/')
    else:
        return ('%s://%s%s' % (protocol, request.get_host(), request.path)).rstrip('/')


class SwaggerUIView(View):
    def get(self, request, *args, **kwargs):

        if not self.has_permission(request):
            return self.handle_permission_denied(request)

        template_name = SWAGGER_SETTINGS.get('template_path')
        data = {
            'swagger_settings': {
                'discovery_url': "%s/api-docs/" % get_full_base_path(request),
                'api_key': SWAGGER_SETTINGS.get('api_key', ''),
                'token_type': SWAGGER_SETTINGS.get('token_type'),
                'enabled_methods': mark_safe(
                    json.dumps(SWAGGER_SETTINGS.get('enabled_methods'))),
                'doc_expansion': SWAGGER_SETTINGS.get('doc_expansion', ''),
            }
        }
        response = render_to_response(template_name, RequestContext(request, data))

        return response

    def has_permission(self, request):
        if SWAGGER_SETTINGS.get('is_superuser') and not request.user.is_superuser:
            return False

        if SWAGGER_SETTINGS.get('is_authenticated') and not request.user.is_authenticated():
            return False

        return True

    def handle_permission_denied(self, request):
        permission_denied_handler = SWAGGER_SETTINGS.get('permission_denied_handler')
        if isinstance(permission_denied_handler, six.string_types):
            permission_denied_handler = import_string(permission_denied_handler)

        if permission_denied_handler:
            return permission_denied_handler(request)
        else:
            raise PermissionDenied()


class SwaggerResourcesView(APIDocView):
    renderer_classes = (JSONRenderer,)

    def get(self, request):
        apis = []
        resources = self.get_resources()

        for path in resources:
            apis.append({
                'path': "/%s" % path,
            })

        return Response({
            'apiVersion': SWAGGER_SETTINGS.get('api_version', ''),
            'swaggerVersion': '1.2',
            'basePath': self.get_base_path(),
            'apis': apis,
            'info': SWAGGER_SETTINGS.get('info', {
                'contact': '',
                'description': '',
                'license': '',
                'licenseUrl': '',
                'termsOfServiceUrl': '',
                'title': '',
            }),
        })

    def get_base_path(self):
        protocol = SWAGGER_SETTINGS.get('protocol', 'http')
        if 'base_path' in SWAGGER_SETTINGS:
            return ("%s://%s/api-docs" % (protocol, SWAGGER_SETTINGS.get('base_path', '').rstrip('/')))
        else:
            return ('%s://%s%s' % (protocol, self.request.get_host(), self.request.path)).rstrip('/')

    def get_resources(self):
        urlparser = UrlParser()
        urlconf = getattr(self.request, "urlconf", None)
        apis = urlparser.get_apis(urlconf=urlconf, exclude_namespaces=SWAGGER_SETTINGS.get('exclude_namespaces'))
        resources = urlparser.get_top_level_apis(apis)
        return resources


class SwaggerApiView(APIDocView):
    renderer_classes = (JSONRenderer,)

    def get(self, request, path):
        apis = self.get_api_for_resource(path)
        generator = DocumentationGenerator()

        return Response({
            'apiVersion': SWAGGER_SETTINGS.get('api_version', ''),
            'swaggerVersion': '1.2',
            'basePath': self.api_full_uri.rstrip('/'),
            'resourcePath': '/' + path,
            'apis': generator.generate(apis),
            'models': generator.get_models(apis),
        })

    def get_api_for_resource(self, filter_path):
        urlparser = UrlParser()
        urlconf = getattr(self.request, "urlconf", None)
        return urlparser.get_apis(urlconf=urlconf, filter_path=filter_path)
