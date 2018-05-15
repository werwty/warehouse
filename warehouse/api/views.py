import datetime
from pyramid.view import view_config
from sqlalchemy import func, desc, orm
from warehouse.packaging.models import (Project, JournalEntry,
                                        Role, User, Release)


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

    projects = projects.order_by(Project.id).all()
    return [_render_project(request, project) for project in projects]


@view_config(
    route_name="api.views.projects.detail",
    renderer="json",
)
def projects_detail(project, request):
    return _render_project(request, project)


@view_config(
    route_name="api.views.projects.detail.roles",
    renderer="json"
)
def projects_detail_roles(project, request):
    roles = (
        request.db.query(Role)
                  .join(User, Project)
                  .filter(Project.normalized_name ==
                          func.normalize_pep426_name(project.name))
                  .order_by(Role.role_name.desc(), User.username)
                  .all()
    )
    return [{"role": r.role_name, "name": r.user.username} for r in roles]


@view_config(
    route_name="api.views.projects.releases.details",
    renderer="json"
)
def projects_details_versions_details(release, request):
    project = release.project
    try:
        release = (
            request.db.query(Release).options(orm.undefer("description"))
                .join(Project)
                .filter((Project.normalized_name ==
                         func.normalize_pep426_name(project.name)) &
                        (Release.version == release.version)).one()
        )
    except orm.exc.NoResultFound:
        return {}

    return {
        "name": release.project.name,
        "version": release.version,
        "stable_version": release.project.stable_version,
        "bugtrack_url": release.project.bugtrack_url,
        "package_url": request.route_url(
            "api.views.projects.detail",
            name=release.project.name,
        ),
        "release_url": request.route_url(
            "api.views.projects.releases.details",
            name=release.project.name,
            version=release.version,
        ),
        "docs_url": release.project.documentation_url,
        "home_page": release.home_page,
        "download_url": release.download_url,
        "project_url": list(release.project_urls),
        "author": release.author,
        "author_email": release.author_email,
        "maintainer": release.maintainer,
        "maintainer_email": release.maintainer_email,
        "summary": release.summary,
        "description": release.description,
        "license": release.license,
        "keywords": release.keywords,
        "platform": release.platform,
        "classifiers": list(release.classifiers),
        "requires": list(release.requires),
        "requires_dist": list(release.requires_dist),
        "provides": list(release.provides),
        "provides_dist": list(release.provides_dist),
        "obsoletes": list(release.obsoletes),
        "obsoletes_dist": list(release.obsoletes_dist),
        "requires_python": release.requires_python,
        "requires_external": list(release.requires_external),
        "_pypi_ordering": release._pypi_ordering,
        "_pypi_hidden": release._pypi_hidden,
        "downloads": {
            "last_day": -1,
            "last_week": -1,
            "last_month": -1,
        },
        "cheesecake_code_kwalitee_id": None,
        "cheesecake_documentation_id": None,
        "cheesecake_installability_id": None,
    }


#
# @view_config(
#     route_name="api.views.projects.detail.versions.detail.download_urls",
#     renderer="json",
#     context=Release,
#
# )
# def projects_versions_downloads(version, request):
#     project = version.project
#
#     files = (
#         request.db.query(File)
#             .join(Release, Project)
#             .filter((Project.normalized_name ==
#                      func.normalize_pep426_name(project.name)) &
#                     (Release.version == version))
#             .all()
#     )
#
#     return [
#         {
#             "filename": f.filename,
#             "packagetype": f.packagetype,
#             "python_version": f.python_version,
#             "size": f.size,
#             "md5_digest": f.md5_digest,
#             "sha256_digest": f.sha256_digest,
#             "digests": {
#                 "md5": f.md5_digest,
#                 "sha256": f.sha256_digest,
#             },
#             "has_sig": f.has_signature,
#             "upload_time": f.upload_time.isoformat() + "Z",
#             "comment_text": f.comment_text,
#             # TODO: Remove this once we've had a long enough time with it
#             #       here to consider it no longer in use.
#             "downloads": -1,
#             "path": f.path,
#             "url": request.route_url("packaging.file", path=f.path),
#         }
#         for f in files
#     ]

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


@view_config(
    route_name="api.views.users.details.projects",
    renderer="json"
)
def user_detail_packages(user, request):
    roles = request.db.query(Role).join(User, Project)\
        .filter(User.username == user.username)\
        .order_by(Role.role_name.desc(), Project.name).all()

    return [{"role": r.role_name, "project": r.project.name} for r in roles]
