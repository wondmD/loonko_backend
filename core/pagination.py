from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000

    def get_page_size(self, request):
        # Support either ?page_size= or ?limit= query params
        if 'limit' in request.query_params and 'page_size' not in request.query_params:
            try:
                limit_val = int(request.query_params['limit'])
                if limit_val > 0:
                    return min(limit_val, self.max_page_size)
            except (ValueError, TypeError):
                pass
        return super().get_page_size(request)
