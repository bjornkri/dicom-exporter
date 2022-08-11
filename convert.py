from curses import window
import os
import requests
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

def retrieve_pseudo_dicom_url(case_identifier: str):
    with Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        task1 = progress.add_task(description='Fetching case...', total=1)
        headers = {'Authorization': f'Token {TOKEN}'}
        case_r = requests.get(f'{SERVER}{CASESLIST}',
            params={'case_identifier': case_identifier},
            headers=headers)
        study_id = case_r.json()['results'][0]['studyId']
        progress.advance(task1)

        task2 = progress.add_task(description='Locating DICOM...', total=1)
        studyresource_r = requests.get(f'{SERVER}{STUDYRESOURCELIST}',
            params={'type': 1, 'studyId': study_id},
            headers=headers)
        studyresource_url = studyresource_r.json()['results'][0]['readUrl']
        progress.advance(task2)
    return studyresource_url


def download_pseudo_dicom(case_identifier: str, url: str):
    r = requests.get(url, stream=True)
    path = f'{case_identifier}.zip'
    with open(path, 'wb') as f, Progress(
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
    extract_path = 'ziptest'
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


@app.command()
def main(case_identifier: str):
    # url = retrieve_pseudo_dicom_url(case_identifier)
    # dicom_filename = download_pseudo_dicom(case_identifier, url)
    dicom_filename = f'{case_identifier}.zip'
    extracted_dicom_path = extract(dicom_filename)
    levels = determine_levels(extracted_dicom_path)
    print(levels)
    with Progress(
        SpinnerColumn(finished_text="✔️"),
        TextColumn("[progress.description]{task.description}"),
    ) as progress:
        convert = progress.add_task("Converting...", total=1)
        convertDICOMVolumeToVTKFile(
            extracted_dicom_path,
            'outputs/output.vtkjs',
            overwrite=True
        )
        progress.advance(convert)



if __name__ == '__main__':
    app()
