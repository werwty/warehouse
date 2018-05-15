from pyramid.view import view_config

from warehouse.packaging.models import File, Release, Project

def _render_project(request, project):
    return {
    "name": project.normalized_name,
    "serial": project.last_serial,
    "project_url": request.route_url(
        "api.views.projects.detail",
        name=project.name,
        )
    }

@view_config(
    route_name="api.views.projects",
    renderer="json",
)
def projects(request):
    projects = request.db.query(Project).order_by(Project.normalized_name).all()
    return [_render_project(request, project) for project in projects]


@view_config(
    route_name="api.views.projects.detail",
    renderer="json",
)
def projects_detail(project, request):
    return _render_project(request, project)
