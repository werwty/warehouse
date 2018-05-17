import datetime

from marshmallow import Schema, fields
from paginate_sqlalchemy import SqlalchemyOrmPage as SQLAlchemyORMPage
from pyramid.view import view_config
from sqlalchemy import func, orm

from warehouse.packaging.models import (Project, JournalEntry,
                                        Role, User, Release, File)
from warehouse.utils.paginate import paginate_url_factory
from warehouse.api.utils import pagination_serializer

# Should this move to a config?
ITEMS_PER_PAGE = 100


class ProjectSchema(Schema):
    normalized_name = fields.Str()
    url = fields.Method('get_detail_url')
    last_serial = fields.Int()

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


class ReleaseSchema(Schema):
    name = fields.Str(attribute='project.name')
    version = fields.Str()
    summary = fields.Str()
    description_content_type = fields.Str()
    description = fields.Str()
    keywords = fields.Str()
    license = fields.Str()
    # "classifiers": list(release.classifiers),
    classifiers = fields.Str(many=True)
    author = fields.Str()
    author_email = fields.Str()
    maintainer = fields.Str()
    maintainer_email = fields.Str()
    requires_python = fields.Str()
    platform = fields.Str()
    files = fields.Nested('FileSchema', many=True)


class FileSchema(Schema):
    filename = fields.Str()
    packagetype = fields.Str()
    python_version = fields.Str()
    has_sig = fields.Bool(attribute='has_signature')
    comment_text = fields.Str()
    md5_digest = fields.Str()
    digests = fields.Method('get_digests')
    size = fields.Int()
    # TODO: Remove this once we've had a long enough time with it
    #       here to consider it no longer in use.
    downloads = fields.Function(lambda obj: -1)
    upload_time = fields.Function(lambda obj: obj.upload_time.strftime("%Y-%m-%dT%H:%M:%S"))
    url = fields.Method('get_detail_url')

    def get_digests(self, obj):
        return {'md5': obj.md5_digest,
                'sha256': obj.sha256_digest}

    def get_detail_url(self, obj):
        request = self.context.get('request')
        return request.route_url("packaging.file", path=obj.path)


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
    request.response.headers["X-PyPI-Last-Serial"] = str(project.last_serial)
    release_schema = ReleaseSchema()
    release_schema.context = {'request': request}
    return {'info': release_schema.dump(release)}


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
