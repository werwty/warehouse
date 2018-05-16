def pagination_serializer(schema, data, route, request):
    extra_filters = ""
    for key, value in request.params.items():
        if key != "page":
            extra_filters = "{filters}&{key}={value}".format(filters=extra_filters,
                                                             key=key,
                                                             value=value)
    resource_url = request.route_url(route)
    url_template = "{url}?page={page}{extra_filters}"

    next_page = None
    if data.next_page:
        next_page = url_template.format(url=resource_url, page=data.next_page,
                                        extra_filters=extra_filters)
    previous_page = None
    if data.previous_page:
        previous_page = url_template.format(url=resource_url, page=data.previous_page,
                                            extra_filters=extra_filters)

    return {
        "data": schema.dump(data),
        "links": {
            "next_page": next_page,
            "previous_page": previous_page
        }
    }
