import datetime
from pyramid.view import view_config
from sqlalchemy import func, desc
from warehouse.packaging.models import Project, JournalEntry


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
    serial_since = request.params.get("serial_since")
    serial = request.params.get("serial")
    projects = request.db.query(Project)

    if serial_since:
        projects = projects.filter(Project.last_serial >= serial_since)
    if serial:
        projects = projects.filter(Project.last_serial == serial)

    projects = projects.order_by(Project.normalized_name).all()
    return [_render_project(request, project) for project in projects]


@view_config(
    route_name="api.views.projects.detail",
    renderer="json",
)
def projects_detail(project, request):
    return _render_project(request, project)


@view_config(
    route_name="api.views.journals",
    renderer="json",
)
def journals(request):
    journals = request.db.query(JournalEntry).order_by(desc(JournalEntry.submitted_date)) \
        .limit(1000).all()

    return [
        {"name": journal.name,
         "version": journal.version,
         "timestamp": journal.submitted_date
            .replace(tzinfo=datetime.timezone.utc).timestamp(),
         "action": journal.action}
        for journal in journals]


@view_config(
    route_name="api.views.journals.latest",
    renderer="json",
)
def journals_latest(request):
    last_serial = request.db.query(func.max(JournalEntry.id)).scalar()
    response = {
        "last_serial": last_serial,
        "project_url": request.route_url(
            "api.views.projects",
            _query={'serial': last_serial}
        )
    }
    return response
