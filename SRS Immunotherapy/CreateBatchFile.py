# file management
import os
import flywheel

import pandas as pd

import csv

os.environ['FLYWHEEL_SDK_REQUEST_TIMEOUT'] = '600'
os.environ['FLYWHEEL_SDK_CONNECT_TIMEOUT'] = '600'

# initialize the file paths to hold all the images separated by sequence and SRS Date
root = '/shares/mimrtl/Users/Chengnan/SRS_Immunotherapy'
PreT1Bravo_path = os.path.join(root, 'PreT1Bravo_Immuno');
if not os.path.isdir(PreT1Bravo_path):
    os.mkdir(PreT1Bravo_path)

PreT1Vasc_path = os.path.join(root, 'PreT1Vasc_Immuno');
if not os.path.isdir(PreT1Vasc_path):
    os.mkdir(PreT1Vasc_path)

PreT2Flair_path = os.path.join(root, 'PreT2Flair_Immuno');
if not os.path.isdir(PreT2Flair_path):
    os.mkdir(PreT2Flair_path)

Post3MoT1Bravo_path = os.path.join(root, 'Post3MoT1Bravo_Immuno');
if not os.path.isdir(Post3MoT1Bravo_path):
    os.mkdir(Post3MoT1Bravo_path)

Post3MoT1Vasc_path = os.path.join(root, 'Post3MoT1Vasc_Immuno');
if not os.path.isdir(Post3MoT1Vasc_path):
    os.mkdir(Post3MoT1Vasc_path)

Post3MoT2Flair_path = os.path.join(root, 'Post3MoT2Flair_Immuno');
if not os.path.isdir(Post3MoT2Flair_path):
    os.mkdir(Post3MoT2Flair_path)

# initialize flywheel variables
fw = flywheel.Client('flywheel.uwhealth.org:0tfO3O6KmTcoy0fVxM')
FW_GROUP = 'baschnagelgroup'
FW_PROJECT = 'SRS Immunotherapy Project'
image_path = root + 'Image_Data_Immuno'
if not os.path.isdir(image_path):
    os.mkdir(image_path)
fw_group = fw.lookup( FW_GROUP )
fw_project = fw_group.projects.find_first('label={}'.format(FW_PROJECT))


def get_or_create_session(subject, label, update=True, **kwargs):
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
        session = subject.add_session(label=label)

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

# read in excel spreadsheet of patients documented with all three registration files
df = pd.read_excel(os.path.join(root, 'ImmunoReg.xlsx'), index_col = 0)

# Create a list of all subjects in the spreadsheet
ValidSubjects = []
for _, row in df.iterrows():
    # add a 0 to the front of subject name if the length is less than 7
    key = str(row.name) if len(str(row.name)) == 7 else '0' + str(row.name)
    ValidSubjects.append(key)


def createBatchFile(base, batchFileName, missingFileName, SRSStatus, sequence):
    """Creates a batch file for an imaging sequence and updates any missing information

    Args:
        base: path file to hold all the data
        batchFileName: name of csv to write to
        missingFileName: name of file to write to for all missing info
        SRSStatus: SRS Status of the sequence (either 'Pre':Pre-SRS or 'Post3Mo':Post 3 Month SRS)
        sequence: Name of the sequence (either 'T1StealthBravo', 'T1CubeVasc', or 'T2CubeFlair')
    """
    print('Creating batch file with image and mask path pairs: ', batchFileName)
    with open(batchFileName, 'w', newline='') as f, open(missingFileName, 'a', newline='') as m:
        writer = csv.writer(f)
        writer.writerow(["Image", "Mask"])
        fw_subjects = fw_project.subjects.iter()
        for fw_subject in fw_subjects:
            subject = fw_subject.label
            # skip subject if not in list
            if subject not in ValidSubjects:
                continue

            subject_path = os.path.join(base, subject)
            if not os.path.isdir(subject_path):
                os.mkdir(subject_path)

            new_session = get_or_create_session(fw_subject, "Extracted ROIs and Registered Files")
            if SRSStatus == 'Pre':
                image_acquisition = get_or_create_acquisition(new_session, 'Pre-Treatment')
            elif SRSStatus == 'Post3Mo':
                image_acquisition = get_or_create_acquisition(new_session, 'Post3Mo-Treatment')
            mask_acquisition = get_or_create_acquisition(new_session, 'Extracted ROIs')

            image_path = ''
            mask_paths = []

            for f in image_acquisition.files:
                if sequence in f.name:
                    image_path = os.path.join(subject_path, f.name)
                    if not os.path.exists(image_path):
                        image_acquisition.download_file(f.name, image_path)

            for mask in mask_acquisition.files:
                if 'ptv' in mask.name:
                    ptv_path = os.path.join(subject_path, mask.name)
                    if not os.path.exists(ptv_path):
                        mask_acquisition.download_file(mask.name, ptv_path)
                    mask_paths.append(ptv_path)

            if image_path and mask_paths:
                print("Writing", image_path)
                for mask_path in mask_paths:
                    writer.writerow([image_path, mask_path])
                    print("Writing", mask_path)
            if not image_path:
                print('{}-SRS {} sequence does not exist for patient {}\n'.format(SRSStatus, sequence, subject))
                m.write('{}-SRS {} sequence does not exist for patient {}\n'.format(SRSStatus, sequence, subject))
            if not mask_paths and SRSStatus == 'Pre' and sequence == 'T1StealthBravo':  # only want to write this once
                print('No ptv masks for patient {}\n'.format(subject))
                m.write('No ptv masks for patient {}\n'.format(subject))

# Create Batch File for all the sequences and for all the SRS Statuses
missingFile = os.path.join(root, 'missingFiles.csv')
createBatchFile(PreT1Bravo_path, os.path.join(PreT1Bravo_path, 'PreT1Bravo_batchFile.csv'), missingFile, 'Pre', 'T1StealthBravo')
createBatchFile(PreT1Vasc_path, os.path.join(PreT1Vasc_path, 'PreT1Vasc_batchFile.csv'), missingFile, 'Pre', 'T1CubeVasc')
createBatchFile(PreT2Flair_path, os.path.join(PreT2Flair_path, 'PreT2Flair_batchFile.csv'), missingFile, 'Pre', 'T2CubeFlair')
createBatchFile(Post3MoT1Bravo_path, os.path.join(Post3MoT1Bravo_path, 'Post3MoT1Bravo_batchFile.csv'), missingFile, 'Post3Mo', 'T1StealthBravo')
createBatchFile(Post3MoT1Vasc_path, os.path.join(Post3MoT1Vasc_path, 'Post3MoT1Vasc_batchFile.csv'), missingFile, 'Post3Mo', 'T1CubeVasc')
createBatchFile(Post3MoT2Flair_path, os.path.join(Post3MoT2Flair_path, 'Post3MoT2Flair_batchFile.csv'), missingFile, 'Post3Mo', 'T2CubeFlair')

