# importing neccessary libraries

from DicomRTTool.ReaderWriter import DicomReaderWriter

# file management
import os
os.environ['FLYWHEEL_SDK_REQUEST_TIMEOUT'] = '600'
os.environ['FLYWHEEL_SDK_CONNECT_TIMEOUT'] = '600'

import flywheel
import zipfile
import gzip
import shutil
from six.moves import urllib
import flywheel

# array manipulation and plotting
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# medical image manipulation
import SimpleITK as sitk

# image registration
import ants

import pandas

root = '/shares/mimrtl/Users/Chengnan'
nifti_path = root + 'Nifti_Data'
if not os.path.isdir(nifti_path):
    os.mkdir(nifti_path)

# initialize flywheel variables
fw = flywheel.Client('flywheel.uwhealth.org:0tfO3O6KmTcoy0fVxM')
FW_GROUP = 'baschnagelgroup'
FW_PROJECT = 'SRS Necrosis Project'
image_path = root + 'Image_Data'
if not os.path.isdir(image_path):
    os.mkdir(image_path)
fw_group = fw.lookup( FW_GROUP )
fw_project = fw_group.projects.find_first('label={}'.format(FW_PROJECT))
fw_subjects = fw_project.subjects.iter()


def get_subject(project, label, update=True, **kwargs):
    """Get the Subject container if it exists, else create a new Subject container.

    Args:
        project (flywheel.Project): A Flywheel Project.
        label (str): The subject label.
        update (bool): If true, update container with key/value passed as kwargs.
        kwargs (dict): Any key/value properties of subject you would like to update.

    Returns:
        (flywheel.Subject): A Flywheel Subject container.
    """

    if not label:
        raise ValueError(f'label is required (currently {label})')

    subject = project.subjects.find_first('label="{}"'.format(label))
    if not subject:
        raise ValueError(f'subject {label} is not found')

    if update and kwargs:
        subject.update(**kwargs)

    if subject:
        subject = subject.reload()

    return subject


def get_session(subject, label, update=True, **kwargs):
    """Get the Session container if it exists, else create a new Session container.

    Args:
        subject (flywheel.Subject): A Flywheel Subject.
        label (str): The session label.
        update (bool): If true, update container with key/value passed as kwargs.
        kwargs (dict): Any key/value properties of Session you would like to update.

    Returns:
        (flywheel.Session): A flywheel Session container.
    """

    if not label:
        raise ValueError(f'label is required (currently {label})')

    session = subject.sessions.find_first('label="{}"'.format(label))
    if not session:
        raise ValueError(f'session {label} is not found')

    if update and kwargs:
        session.update(**kwargs)

    if session:
        session = session.reload()

    return session


def get_or_create_acquisition(session, label, update=True, **kwargs):
    """Get the Acquisition container if it exists, else create a new Acquisition container.

    Args:
        session (flywheel.Session): A Flywheel Session.
        label (str): The Acquisition label.
        update (bool): If true, update container with key/value passed as kwargs.
        kwargs (dict): Any key/value properties of Acquisition you would like to update.

    Returns:
        (flywheel.Acquisition): A Flywheel Acquisition container.
    """

    if not label:
        raise ValueError(f'label is required (currently {label})')

    acquisition = session.acquisitions.find_first('label="{}"'.format(label))
    if not acquisition:
        acquisition = session.add_acquisition(label=label)

    if update and kwargs:
        acquisition.update(**kwargs)

    if acquisition:
        acquisition = acquisition.reload()

    return acquisition


def upload_file_to_acquisition(acquisition, fp, update=True, **kwargs):
    """Upload file to Acquisition container and update info if `update=True`

    Args:
        acquisition (flywheel.Acquisition): A Flywheel Acquisition
        fp (Path-like): Path to file to upload
        update (bool): If true, update container with key/value passed as kwargs.
        kwargs (dict): Any key/value properties of Acquisition you would like to update.
    """
    basename = os.path.basename(fp)
    if not os.path.isfile(fp):
        raise ValueError(f'{fp} is not file.')
    attempts = 0

    while attempts < 5:
        try:
            acquisition = acquisition.reload()
            if acquisition.get_file(basename):
                print('file {} already exists'.format(fp))
                return
            else:
                print('uploading', fp)
                acquisition.upload_file(fp)
            #                 while not acquistion.get_file(basename):   # to make sure the file is available before performing an update
            #                     acquistion = acquistion.reload()
            #                     time.sleep(1)
            break
        except Exception as e:
            print('Error exception caught!')
            print(e)
            attempts += 1

    if update and kwargs:
        f = acquisition.get_file(basename)
        f.update(**kwargs)

def changeFileName(file):
    number, name = file.split("-")
    name = name.strip()
    name = name.replace(" ", "_")
    name = name + "_" + number.strip()
    return name

# read in excel spreadsheet of patients documented with all three registration files
df = pandas.read_excel('/Users/cxl037/PycharmProjects/pythonProject1/CompleteRegistration.xlsx', index_col = 0)

# create a dictionary with patient and corresponding registration files
allRegfiles = {}
for _, row in df.iterrows():
    # key is obtained by combining subject name and session name
    key = str(row.name) + '_' + str(row['MRI_Date'])
    key = key[:-9]

    # special formatting for this patient
    if key == '1150651_2021-12-17':
        allRegfiles[key] = []
        allRegfiles[key].append('MR.nii')
        allRegfiles[key].append('MR.nii')
        allRegfiles[key].append('MR.nii')
        continue

    # add each of the 3 files to the list for the key
    allRegfiles[key] = []
    allRegfiles[key].append(changeFileName(row['"+c Ax T1 Stealth bravo"']))
    allRegfiles[key].append(changeFileName(row['"+c COR T1 CUBE VASC"']))
    allRegfiles[key].append(changeFileName(row['"+c Sag CUBE T2 FLAIR"']))

# iterate through each subject
for subject in os.listdir(image_path):
    if subject != '.DS_Store':
        subject_path = os.path.join(image_path, subject)
    # iterate through each session in the subject
    for session in os.listdir(subject_path):
        if session != '.DS_Store':
            session_path = os.path.join(subject_path, session)

        # Intialize the Dicom_reader and walk it through the session folders
        Dicom_reader = DicomReaderWriter(description='RTStructExtractor', arg_max=True, verbose=False)
        try:
            Dicom_reader.walk_through_folders(session_path)
        except Exception as e:
            print(e)

        all_rois = Dicom_reader.return_rois(print_rois=True)  # Return a list of all rois present, and print them

        # if there are no ROIs, then skip
        if not all_rois:
            print("Skip session {} because no rois".format(session))
            continue

        # otherwise create a new acquisition
        fw_subject = get_subject(fw_project, subject)
        fw_session = get_session(fw_subject, session)
        fw_acquisition = get_or_create_acquisition(fw_session, 'Extracted ROIs')

        # key for the dictionary
        key = subject + '_' + session[:10]

        # parse through subjects with all the Registration files
        if key in allRegfiles.keys():
            T1StealthBravo = ''
            T1CubeVasc = ''
            T2CubeFlair = ''
            # go through all the files in the session and if the file is a registration file, then initialize it correspondingly
            for file in os.listdir(session_path):
                regfiles = allRegfiles[key]
                if regfiles[0] in file:
                    T1StealthBravo = os.path.join(session_path, file)
                if regfiles[1] in file:
                    T1CubeVasc = os.path.join(session_path, file)
                if regfiles[2] in file:
                    T2CubeFlair = os.path.join(session_path, file)

            # all of the files were found and are not empty
            if T1StealthBravo and T1CubeVasc and T2CubeFlair:
                # read files into antspy
                try:
                    fixed = ants.image_read(T1StealthBravo)
                    moving = ants.image_read(T1CubeVasc)
                    moving2 = ants.image_read(T2CubeFlair)
                except Exception as e:
                    print(e)
                    continue

                # register T1CubeVasc to T1StealthBravo
                regT1CubeVasc = ants.registration(fixed=fixed, moving=moving, type_of_transform='Similarity')

                # register T2CubeFlair to T1StealthBravo
                regT2CubeFlair = ants.registration(fixed=fixed, moving=moving2, type_of_transform='Similarity')

                # output path to write registered files to
                output_path = os.path.join(nifti_path, '{}_T1CubeVasc.nii'.format(subject))
                output_path2 = os.path.join(nifti_path, '{}_T2CubeFlair.nii'.format(subject))

                # write the registered files with forward transform to output path
                ants.image_write(regT1CubeVasc['warpedmovout'], output_path)
                ants.image_write(regT2CubeFlair['warpedmovout'], output_path2)

                # upload files to the newly created acquisition
                upload_file_to_acquisition(fw_acquisition, output_path)
                upload_file_to_acquisition(fw_acquisition, output_path2)

        # for each of the rois, create a nifti file for the extracted roi
        for roi in all_rois:
            # initialize the contour_names and associations
            # Associations work as {'variant_name': 'desired_name'}
            Contour_Names = [roi]
            associations = {roi: roi}
            Dicom_reader.set_contour_names_and_associations(Contour_Names=Contour_Names, associations=associations)

            # get the images and mask which have this roi
            indexes = Dicom_reader.which_indexes_have_all_rois()
            pt_indx = indexes[0]
            Dicom_reader.set_index(pt_indx)
            Dicom_reader.get_images_and_mask()
            dicom_sitk_handle = Dicom_reader.dicom_handle  # SimpleITK image handle
            mask_sitk_handle = Dicom_reader.annotation_handle  # SimpleITK mask handle

            # Get the base image for the mask
            base_image = Dicom_reader.series_instances_dictionary[pt_indx]['Description'].strip()

            # write the image to the output nifti path
            image_nifti_path = os.path.join(nifti_path, '{}_{}.nii'.format(subject, base_image))
            mask_nifti_path = os.path.join(nifti_path, '{}_{}_Mask.nii'.format(subject, roi))
            sitk.WriteImage(dicom_sitk_handle, image_nifti_path)
            sitk.WriteImage(mask_sitk_handle, mask_nifti_path)

            # upload extracted rois to the newly created acquisition
            upload_file_to_acquisition(fw_acquisition, image_nifti_path)
            upload_file_to_acquisition(fw_acquisition, mask_nifti_path)
