import json
import datetime
from marshmallow import Schema, fields
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.view import view_config
from sqlalchemy import func, desc, orm
from warehouse.packaging.models import (Project, JournalEntry,
                                        Role, User, Release, File)
from sqlalchemy import func, desc
from warehouse.packaging.models import Project, JournalEntry
from warehouse.utils.paginate import paginate_url_factory

from .utils import pagination_serializer

# TODO move this to config
ITEMS_PER_PAGE = 100


class ProjectSchema(Schema):
    normalized_name = fields.Str()
    url = fields.Method("get_detail_url")

    def get_detail_url(self, obj):
        request = self.context.get('request')
        return request.route_url("api.views.projects.detail", name=obj.normalized_name)


@view_config(
    route_name="api.views.projects",
    renderer="json",
)
def projects(request):
    serial_since = request.params.get("serial_since")
    serial = request.params.get("serial")
    page_num = int(request.params.get("page", 1))
    projects_query = request.db.query(Project).order_by(Project.created)

    if serial_since:
        projects_query = projects_query.filter(Project.last_serial >= serial_since)
    if serial:
        projects_query = projects_query.filter(Project.last_serial == serial)

    projects_page = SQLAlchemyORMPage(
        projects_query,
        page=page_num,
        items_per_page=ITEMS_PER_PAGE,
        url_maker=paginate_url_factory(request),
    )
    project_schema = ProjectSchema(many=True)
    project_schema.context = {'request': request}
    return pagination_serializer(project_schema, projects_page, "api.views.projects", request)


@view_config(
    route_name="api.views.projects.detail",
    renderer="json",
    context=Project,
)
def projects_detail(project, request):
    release = (
        request.db.query(Release)
            .filter(Release.project == project)
            .order_by(
            Release.is_prerelease.nullslast(),
            Release._pypi_ordering.desc())
            .limit(1)
            .one()
    )
    return json_release(release, request)


def json_release(release, request):
    project = release.project

    # Get the latest serial number for this project.
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)

    # Get all of the releases and files for this project.
    release_files = (
        request.db.query(Release, File)
               .options(orm.Load(Release).load_only('version'))
               .outerjoin(File)
               .filter(Release.project == project)
               .order_by(Release._pypi_ordering.desc(), File.filename)
               .all()
    )

    # Map our releases + files into a dictionary that maps each release to a
    # list of all its files.
    releases = {}
    for r, file_ in release_files:
        files = releases.setdefault(r, [])
        if file_ is not None:
            files.append(file_)

    # Serialize our database objects to match the way that PyPI legacy
    # presented this data.
    releases = {
        r.version: [
            {
                "filename": f.filename,
                "packagetype": f.packagetype,
                "python_version": f.python_version,
                "has_sig": f.has_signature,
                "comment_text": f.comment_text,
                "md5_digest": f.md5_digest,
                "digests": {
                    "md5": f.md5_digest,
                    "sha256": f.sha256_digest,
                },
                "size": f.size,
                # TODO: Remove this once we've had a long enough time with it
                #       here to consider it no longer in use.
                "downloads": -1,
                "upload_time": f.upload_time.strftime("%Y-%m-%dT%H:%M:%S"),
                "url": request.route_url("packaging.file", path=f.path),
            }
            for f in fs
        ]
        for r, fs in releases.items()
    }

    return {
        "info": {
            "name": project.name,
            "version": release.version,
            "summary": release.summary,
            "description_content_type": release.description_content_type,
            "description": release.description,
            "keywords": release.keywords,
            "license": release.license,
            "classifiers": list(release.classifiers),
            "author": release.author,
            "author_email": release.author_email,
            "maintainer": release.maintainer,
            "maintainer_email": release.maintainer_email,
            "requires_python": release.requires_python,
            "platform": release.platform,
            "downloads": {
                "last_day": -1,
                "last_week": -1,
                "last_month": -1,
            },
            "package_url": request.route_url(
                "packaging.project",
                name=project.name,
            ),
            "project_url": request.route_url(
                "packaging.project",
                name=project.name,
            ),
            "release_url": request.route_url(
                "packaging.release",
                name=project.name,
                version=release.version,
            ),
            "requires_dist": (list(release.requires_dist)
                              if release.requires_dist else None),
            "docs_url": project.documentation_url,
            "bugtrack_url": project.bugtrack_url,
            "home_page": release.home_page,
            "download_url": release.download_url,
        },
        "urls": releases[release.version],
        "releases": releases,
        "last_serial": project.last_serial,
    }


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


@view_config(
    route_name="api.views.journals",
    renderer="json",
)
def journals(request):
    since = request.params.get("since")
    journals = request.db.query(JournalEntry)

    if since:
        journals = journals.filter(
            JournalEntry.submitted_date >
            datetime.datetime.utcfromtimestamp(int(since)))

    journals = journals.order_by(JournalEntry.id).limit(5000)

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
