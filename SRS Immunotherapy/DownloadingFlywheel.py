# importing neccessary libraries

# file management
import os
import zipfile
import flywheel

# initialize the root file
root = '/shares/mimrtl/Users/Chengnan'

# initialize the file path to hold the images (both Dicom and nifti)
image_path = os.path.join(root, 'Image_Data_Immuno');
if not os.path.isdir(image_path):
    os.mkdir(image_path)

# initialize the file path to hold the flywheel data
flywheel_path = os.path.join(root, 'flywheel');
if not os.path.isdir(flywheel_path):
    os.mkdir(flywheel_path)

# initialize flywheel variables
fw = flywheel.Client('flywheel.uwhealth.org:0tfO3O6KmTcoy0fVxM')
FW_GROUP = 'baschnagelgroup'
FW_PROJECT = 'SRS Immunotherapy Project'
fw_group = fw.lookup( FW_GROUP )
fw_project = fw_group.projects.find_first('label={}'.format(FW_PROJECT))
fw_subjects = fw_project.subjects.iter()

# Extract all the flywheel data
for fw_subject in fw_subjects:
    # skip subjects that aren't numeric (i.e. MRI list)
    if not fw_subject.label.isnumeric():
        continue

    # create subject path
    subject_path = os.path.join(image_path, fw_subject.label)
    if not os.path.isdir(subject_path):
        os.mkdir(subject_path)

    # iterate through each session in the subject
    for sess in fw_subject.sessions.iter():
        # create session path
        session_path = os.path.join(subject_path, sess.label)
        if not os.path.isdir(session_path):
            os.mkdir(session_path)
        # iterate through each acquisition in the subject
        for acq in sess.acquisitions.iter():
            # do not reinstall extracted nifti files that have been uploaded
            if acq.label == 'Extracted ROIs':
                continue
            # acquisition path
            acq_path = os.path.join(session_path, acq.label)

            # iterate through each file in the acquisition
            for f in acq.files:
                # download dicom files and put them in the folder
                if f.type == 'dicom':
                    filepath = os.path.join(flywheel_path, '{}_{}'.format(fw_subject.label, f.name))
                    # if dicom file doesn't exist, then unzip them and put into acquisition path
                    if not os.path.exists(filepath):
                        acq.download_file(f.name, filepath)
                        z = zipfile.ZipFile(filepath)
                        z.extractall(acq_path)
                        print('Successfully downloaded file', acq_path)
                # download nifti files and put them in the folder
                if f.type == 'nifti':
                    nifti_path = os.path.join(session_path, f.name)
                    # if nifti file doesn't exist, then download it and put into nifti path
                    if not os.path.exists(nifti_path):
                        acq.download_file(f.name, nifti_path)
                        print('Successfully downloaded file', nifti_path)
    fw_subject = fw_subject.reload()