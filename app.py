import os
import shutil
from functools import wraps

import docker
from flask import Flask
from flask import Response
from flask import request
app = Flask(__name__)


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid.
    """
    valid_uname = username == os.getenv('username', 'admin')
    valid_pass = username == os.getenv('password', 'secretpassword')
    return valid_uname and valid_pass


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return Response(
                'Could not verify your access level for that URL.\n'
                'You have to login with proper credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'}
            )
        return f(*args, **kwargs)
    return decorated


def _format_uuid(uuid):
    return uuid.replace('-', '')


def _get_docker_client():
    """Gets a Docker client, using the configuration defined in environment"""
    tls_config = None
    DOCKER_CERT_PATH = os.getenv('DOCKER_CERT_PATH')
    DOCKER_HOST = os.getenv('DOCKER_HOST', 'unix:///var/run/docker.sock')
    if DOCKER_CERT_PATH:
        tls_config = docker.tls.TLSConfig(
            client_cert=(
                os.path.join(DOCKER_CERT_PATH, 'cert.pem'),
                os.path.join(DOCKER_CERT_PATH, 'key.pem')),
            verify=os.path.join(DOCKER_CERT_PATH, 'ca.pem'),
            assert_hostname=False)
    return docker.Client(base_url=DOCKER_HOST, tls=tls_config)


@app.route('/api/v1.0/cleanup/', methods=['POST'])
def cleanup():
    """
    For the given uuid, cleans up the following:
        - containers
        - networks
        - volumes
        - images
        - project directory
    """
    if not request.json or 'uuid' not in request.json:
        abort(400)
    raw_uuid = request.json['uuid']
    uuid = _format_uuid(raw_uuid)
    cli = _get_docker_client()
    containers = cli.containers(
        filters={
            'label': 'com.docker.compose.project={}'.format(uuid)
        }
    )
    for container in containers:
        cli.remove_container(container, v=True, force=True)
    networks = cli.networks(names=[uuid])
    for network in networks:
        cli.remove_network(network.get('Id'))
    volumes = cli.volumes(filters={'name': uuid}).get('Volumes')
    if volumes:
        for volume in volumes:
            cli.remove_volume(volume.get('Name'))
    images = cli.images(name=(uuid + '*'))
    for image in images:
        tag = image.get('RepoTags')[0]
        if tag:
            cli.remove_image(tag, force=True)
    code_dir = os.path.join('/mnt/stolos', raw_uuid)
    if os.path.exists(code_dir):
        shutil.rmtree(code_dir)
    return ('', 200)

if __name__ == "__main__":
    app.run()
