import glob
import json
import os
import requests
import tempfile
import typer
import zipfile

from dicomexporter.exporter import convertDICOMVolumeToVTKFile
from dicomexporter.dicom import createITKImageReader
from dicomexporter.itk_utils import getMetadata
from rich.progress import Progress, SpinnerColumn, TextColumn, DownloadColumn

app = typer.Typer()

CASESLIST = '/cases/'
STUDYRESOURCELIST = '/study-resources/'
TOKEN = os.getenv('TOKEN')
SERVER = os.getenv('SERVER')
HEADERS = {'Authorization': f'Token {TOKEN}'}


def get_study_id(case_identifier: str):
    with Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        get_case = progress.add_task(description='Fetching case...', total=1)

        case_r = requests.get(f'{SERVER}{CASESLIST}',
            params={'case_identifier': case_identifier},
            headers=HEADERS)
        study_id = case_r.json()['results'][0]['studyId']
        progress.advance(get_case)
    return study_id


def retrieve_pseudo_dicom_url(study_id: str):
    with Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        get_url = progress.add_task(description='Locating DICOM...', total=1)
        studyresource_r = requests.get(f'{SERVER}{STUDYRESOURCELIST}',
            params={'type': 1, 'study_id': study_id},
            headers=HEADERS)
        studyresource_url = studyresource_r.json()['results'][0]['readUrl']
        progress.advance(get_url)
    return studyresource_url


def download_pseudo_dicom(url: str):
    r = requests.get(url, stream=True)
    fd, path = tempfile.mkstemp(suffix='.zip')
    with os.fdopen(fd, 'wb') as f, Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
        DownloadColumn(),
    ) as progress:
        total_length = int(r.headers.get('content-length'))
        download = progress.add_task("Downloading...", total=total_length)
        while not progress.finished:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk: # filter out keep-alive new chunks
                    progress.update(download, advance=1024)
                    f.write(chunk)
                    f.flush()
    return path


def extract(filename: str):
    extract_path = tempfile.mkdtemp()
    with zipfile.ZipFile(filename, 'r') as zip_ref, Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        extract = progress.add_task("Extracting...", total=1)
        zip_ref.extractall(extract_path)
        progress.advance(extract)
    return extract_path


def firstFloat(v):
  return float(v.split('\\')[0])


def determine_levels(dicom_directory):
    with Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        levels = progress.add_task("Determining levels...", total=1)
        itkReader = createITKImageReader(dicom_directory)
        window_center = getMetadata(itkReader, '0028|1050', firstFloat)
        window_width = getMetadata(itkReader, '0028|1051', firstFloat)
        progress.advance(levels)
    return (window_center, window_width)


def convert(dicom_path):
    output = tempfile.mkdtemp(suffix='.vtkjs')
    with Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        convert = progress.add_task("Converting...", total=1)
        convertDICOMVolumeToVTKFile(
            dicom_path,
            output,
            overwrite=True
        )
        progress.advance(convert)
    return output


def create_study_resource(study_id, source, levels):
    with open(f'{source}/index.json', 'r') as f, Progress(
            SpinnerColumn(finished_text="✔️"),
            TextColumn("[progress.description]{task.description}"),
        ) as progress:
        resource = progress.add_task("Creating studyResource...", total=1)
        attribs = json.load(f)
        attribs['levels'] = [levels[0], levels[1]]
        data = {
            'type': 2, 'studyId': study_id, 'attributes': attribs,
            'metadata': {
                'mime_type': 'application/gzip',
            },
            'name': 'vtkjs',
        }
        studyresource_r = requests.post(f'{SERVER}{STUDYRESOURCELIST}',
            json=data,
            headers=HEADERS)
        progress.advance(resource)
    return studyresource_r.json()


def upload_volume_to(url, source):
    dicom_path = f'{source}/data/'
    name = glob.glob(f'{dicom_path}*.gz')[0].split('/')[-1]

    with open(f'{dicom_path}{name}', 'rb') as data, Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        upload = progress.add_task("Uploading vtkjs...", total=1)
        requests.put(
            url, data=data,
        )
        progress.advance(upload)


@app.command()
def main(case_identifier: str):
    study_id = get_study_id(case_identifier)
    url = retrieve_pseudo_dicom_url(study_id)
    dicom_filename = download_pseudo_dicom(url)
    extracted_dicom_path = extract(dicom_filename)
    levels = determine_levels(extracted_dicom_path)
    converted_dicom = convert(extracted_dicom_path)
    sr = create_study_resource(study_id, converted_dicom, levels)
    upload_volume_to(sr['writeUrl'], converted_dicom)


if __name__ == '__main__':
    app()
