# importing neccessary libraries
from DicomRTTool.ReaderWriter import DicomReaderWriter

# file management
import os
import zipfile
import flywheel

# array manipulation and plotting
import pandas as pd

# medical image manipulation
import SimpleITK as sitk

# image registration
import ants

# string regex
import re

# make timeout longer
os.environ['FLYWHEEL_SDK_REQUEST_TIMEOUT'] = '600'
os.environ['FLYWHEEL_SDK_CONNECT_TIMEOUT'] = '600'

# initialize the root file
root = '/shares/mimrtl/Users/Chengnan/SRS_Immunotherapy'

# initialize the file path to hold the images (both Dicom and nifti)
image_path = os.path.join(root, 'Image_Data_Immuno');
if not os.path.isdir(image_path):
    os.mkdir(image_path)

# initialize the file path to hold the flywheel data
flywheel_path = os.path.join(root, 'flywheel_Immuno');
if not os.path.isdir(flywheel_path):
    os.mkdir(flywheel_path)

# initialize the file path to hold the nifti data
nifti_path = os.path.join(root, 'Nifti_Data_Immuno');
if not os.path.isdir(nifti_path):
    os.mkdir(nifti_path)

# initialize flywheel variables
fw = flywheel.Client('flywheel.uwhealth.org:0tfO3O6KmTcoy0fVxM')
FW_GROUP = 'baschnagelgroup'
FW_PROJECT = 'SRS Immunotherapy Project'
fw_group = fw.lookup(FW_GROUP)
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

    while attempts < 5: # in case error arises during upload, try multiple times
        try:
            acquisition = acquisition.reload()
            if acquisition.get_file(basename):
                print('file {} already exists'.format(fp))
                return
            else:
                print('uploading', fp)
                acquisition.upload_file(fp)
            break
        except Exception as e:
            print('Error exception caught!')
            print(e)
            attempts += 1

    if update and kwargs:
        f = acquisition.get_file(basename)
        f.update(**kwargs)


def downloadNiftiFile(acq, session_path):
    """Downloads the nifti files in an acquisition

    Args:
        acq (flywheel.Acquisition): A Flywheel Acquisition.
        session_path: session path of the acquisition

    Returns:
        nifti_file: Output file to which nifti file is downloaded to
    """
    acq_path = os.path.join(session_path, acq.label)
    if not os.path.isdir(acq_path):
        os.mkdir(acq_path)
    for f in acq.files:  # iterate through each file in the acquisition
        if f.type == 'nifti':
            nifti_file = os.path.join(acq_path, f.name)
            if not os.path.exists(nifti_file):  # if nifti file doesn't exist, then download and put into nifti path
                attempts = 0
                while attempts < 5:  # in case error arises during download, try multiple times
                    try:
                        acq.download_file(f.name, nifti_file)
                        break
                    except Exception as e:
                        print('Error exception caught!')
                        print(e)
                        attempts += 1
                print('Successfully downloaded file', nifti_file)
            else:  # otherwise, no need to download again
                print('{} already exists'.format(nifti_file))
    return nifti_file


def downloadSequences(sess, regFiles, subject, session_path):
    """Downloads the T1StealthBravo, T1CubeVasc, and T2CubeFlair Sequences in a session for a given subject

    Args:
        sess (flywheel.Session): A Flywheel Session.
        regFiles: dictionary of subject and corresponding information, including file names
        subject: subject number
        session_path: Session path

    Returns:
        T1StealthBravo: File Path for T1StealthBravo, empty string if not present
        T1CubeVasc: File Path for T1CubeVasc, empty string if not present
        T2CubeFlair: File Path for T2CubeFlair, empty string if not present
    """
    print('Finding Imaging Sequences for {}'.format(sess.label))
    T1StealthBravo = T1CubeVasc = T2CubeFlair = ''
    for acq in sess.acquisitions.iter():  # iterate through each acquisition in the session
        acq.label = re.sub('\\s+', ' ', acq.label)  # trim down any extra spaces in the acq name
        if regFiles[subject][1] in acq.label:  # T1StealthBravo
            T1StealthBravo = downloadNiftiFile(acq, session_path)
        elif not pd.isna(regFiles[subject][2]) and regFiles[subject][2] in acq.label:  # T1CubeVasc (some entries in this table are empty)
            T1CubeVasc = downloadNiftiFile(acq, session_path)
        elif regFiles[subject][3] in acq.label:  # T2CubeFlair
            T2CubeFlair = downloadNiftiFile(acq, session_path)
    print()
    return T1StealthBravo, T1CubeVasc, T2CubeFlair


def registration(PreT1StealthBravo, MRISequence, fw_acquisition, subject, SRSStatus, MRISequenceName):
    """Performs registration of a subject's MRI Sequence to its Pre-SRS T1StealthBravo sequence and uploads it to Flywheel

    Args:
        PreT1StealthBravo: Path file for Pre-SRS T1StealthBravo
        MRISequence: Path file for sequence to be registered
        fw_acquisition (flywheel.Acquisition): A Flywheel Acquisition which the files are uploaded to.
        subject: subject number
        SRSStatus: SRS Status of the sequence (either 'Pre':Pre-SRS or 'Post3Mo':Post 3 Month SRS)
        MRISequenceName: Name of the sequence (either 'T1StealthBravo', 'T1CubeVasc', or 'T2CubeFlair')
    """
    print('Performing Registration on {} SRS {} sequence for subject {}'.format(SRSStatus, MRISequenceName, subject))
    output_path = os.path.join(nifti_path, '{}_{}_{}.nii'.format(SRSStatus, subject, MRISequenceName))
    if not os.path.exists(output_path):
        try:
            # read files into antspy
            fixed = ants.image_read(PreT1StealthBravo)
            moving = ants.image_read(MRISequence)
            # register PostSequence to T1StealthBravo
            reg = ants.registration(fixed=fixed, moving=moving, type_of_transform='Similarity')
            # write the registered files with forward transform to output path
            ants.image_write(reg['warpedmovout'], output_path)
            print("Registration of {} successful".format(output_path))
        except Exception as e:
            print(e)
    else:
        print('{} already exists'.format(output_path))
    # upload files to the newly created acquisition
    upload_file_to_acquisition(fw_acquisition, output_path)
    print()


def downloadDicomFiles(sess, session_path):
    """Downloads the dicom files in a session

    Args:
        sess (flywheel.Session): A Flywheel Session.
        session_path: session path
    """
    print('Downloading Dicom Files for session {}'.format(sess.label))
    for acq in sess.acquisitions.iter():
        acq_path = os.path.join(session_path, acq.label)
        if not os.path.isdir(acq_path):
            os.mkdir(acq_path)
        for f in acq.files:  # iterate through each file in the acquisition
            if f.type == 'dicom':  # download dicom files and put them in the folder
                filepath = os.path.join(flywheel_path, '{}_{}'.format(fw_subject.label, f.name))
                if not os.path.exists(filepath):  # if dicom file doesn't exist, then unzip and put into acq path
                    attempts = 0
                    while attempts < 5:  # in case error arises during download, try multiple times
                        try:
                            acq.download_file(f.name, filepath)
                            break
                        except Exception as e:
                            print('Error exception caught!')
                            print(e)
                            attempts += 1
                    z = zipfile.ZipFile(filepath)
                    z.extractall(acq_path)
                    print('Successfully downloaded file', acq_path)
                else:  # otherwise no need to download again
                    print('{} already exists'.format(acq_path))
    print()


def extractROIs(session_path, subject):
    """Extracts the RTStructs of a subject into nifti files for each ROI

    Args:
        session_path: session path where all the RT Structs are contained
        subject: subject number

    Returns:
        CT_path: The base CT image for the RTStructs
        ROIs_path: List containing all the nifti paths of the extracted ROIs
    """
    print('Extracting ROIs for subject {}'.format(subject))
    CT_path = ''
    ROIs_path = [] # list of ROI masks

    # Initialize the Dicom_reader and walk it through the session folders
    Dicom_reader = DicomReaderWriter(description='RTStructExtractor', arg_max=True, verbose=False)
    Dicom_reader.walk_through_folders(session_path)
    all_rois = Dicom_reader.return_rois(print_rois=True)  # Return a list of all rois present, and print them

    if all_rois: # if there are ROIs, then extract the RT structs for each ROI
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
            try:
                Dicom_reader.get_images_and_mask()
                dicom_sitk_handle = Dicom_reader.dicom_handle  # SimpleITK image handle
                mask_sitk_handle = Dicom_reader.annotation_handle  # SimpleITK mask handle

                base_image = Dicom_reader.series_instances_dictionary[pt_indx][
                    'Description'].strip()  # base image for mask

                # initialize output nifti path
                CT_path = os.path.join(nifti_path, '{}_{}.nii'.format(subject, base_image))
                ROI_path = os.path.join(nifti_path, '{}_{}_Mask.nii'.format(subject, roi))
                ROIs_path.append(ROI_path)

                # write the base image to the output nifti path
                if not os.path.exists(CT_path):
                    sitk.WriteImage(dicom_sitk_handle, CT_path)
                    print('Writing image', CT_path)
                else:  # otherwise no need to download again
                    print('{} already exists'.format(CT_path))

                # write the ROI mask to the output nifti path
                if not os.path.exists(ROI_path):
                    sitk.WriteImage(mask_sitk_handle, ROI_path)
                    print('Writing image', ROI_path)
                else:  # otherwise no need to download again
                    print('{} already exists'.format(ROI_path))
            except:  # error when getting the image and mask
                print('{} did not work'.format(roi))
    else: # If no ROIs present, then return
        print("No ROIs")
    print()
    return (CT_path, ROIs_path)


# read in excel spreadsheet of patients documented with all three registration files
df = pd.read_excel(os.path.join(root, 'ImmunoReg.xlsx'), index_col = 0)

# create a dictionary with patient and corresponding registration files
PreSRSRegfiles = {}
Post3MoSRSRegfiles = {}
for _, row in df.iterrows():
    # add a 0 to the front of subject name if the length is less than 7
    key = str(row.name) if len(str(row.name)) == 7 else '0' + str(row.name)

    # Add the dates and the 3 scans
    PreSRSRegfiles[key] = []
    RTStructSession = row['CT Session']
    sessiontime = str(row['Pre-SRS MRI Date'])[:-9]
    PreSRSRegfiles[key].append(sessiontime)
    PreSRSRegfiles[key].append(row['T1 Bravo Stealth (Pre)'])
    PreSRSRegfiles[key].append(row['T1 Cube Vasc (Pre)'])
    PreSRSRegfiles[key].append(row['T2 Cube Flair (Pre)'])
    PreSRSRegfiles[key].append(RTStructSession)

    # Add the dates and the 3 scans
    Post3MoSRSRegfiles[key] = []
    sessiontime = str(row['Date 3-month F/U MRI'])[:-9]
    Post3MoSRSRegfiles[key].append(sessiontime)
    Post3MoSRSRegfiles[key].append(row['T1 Bravo Stealth (3 month)'])
    Post3MoSRSRegfiles[key].append(row['T1 Cube Vasc (3 month)'])
    Post3MoSRSRegfiles[key].append(row['T2 Cube Flair (3 month)'])

# Extract all the flywheel data
fw_subjects = fw_project.subjects.iter()
for fw_subject in fw_subjects:
    # skip subject if not in dict
    if fw_subject.label not in PreSRSRegfiles.keys() or fw_subject.label == '1947241':
        continue

    if fw_subject.label != '0842320':
        continue

    # Initialize paths and variables
    subject = fw_subject.label
    subject_path = os.path.join(image_path, subject)
    if not os.path.isdir(subject_path):
        os.mkdir(subject_path)

    PreT1StealthBravo = ''  # need to store the Pre-SRS T1 Stealth Bravo for registration
    CT_path = ''
    ROIs_path = []
    
    preSessionDate = PreSRSRegfiles[subject][0]
    post3moSessionDate = Post3MoSRSRegfiles[subject][0]
    RTStructSession = PreSRSRegfiles[subject][4]

    if pd.isna(RTStructSession):  # skip if there are no RT structs
        continue

    # Create new sessions and acquisitions
    new_session = get_or_create_session(fw_subject, "Extracted ROIs and Registered Files")
    pre_treat_acquisition = get_or_create_acquisition(new_session, 'Pre-Treatment')
    post3mo_treat_acquisition = get_or_create_acquisition(new_session, 'Post3Mo-Treatment')
    ext_ROI_acquisition = get_or_create_acquisition(new_session, 'Extracted ROIs')

    for sess in fw_subject.sessions.iter(): # iterate through each session in the subject
        if preSessionDate in sess.label:  # Go through the pre-SRS session and retrieve the sequences
            # create session path
            session_path = os.path.join(subject_path, sess.label)
            if not os.path.isdir(session_path):
                os.mkdir(session_path)

            # download and retrieve sequences
            (T1StealthBravo, T1CubeVasc, T2CubeFlair) = downloadSequences(sess, PreSRSRegfiles, subject, session_path)

            if T1StealthBravo:  # perform registration on these files if present
                PreT1StealthBravo = T1StealthBravo
                registration(PreT1StealthBravo, T1StealthBravo, pre_treat_acquisition, subject, 'Pre',
                             'T1StealthBravo')
            if T1CubeVasc:
                registration(PreT1StealthBravo, T1CubeVasc, pre_treat_acquisition, subject, 'Pre',
                             'T1CubeVasc')
            if T2CubeFlair:
                registration(PreT1StealthBravo, T2CubeFlair, pre_treat_acquisition, subject, 'Pre',
                                 'T2CubeFlair')

        if RTStructSession in sess.label:  # Go through the RT Struct session and extract the ROIs
            # create session path
            session_path = os.path.join(subject_path, sess.label)
            if not os.path.isdir(session_path):
                os.mkdir(session_path)

            # download and retrieve dicom files and extract the ROIs
            downloadDicomFiles(sess, session_path)
            (CT_path, ROIs_path) = extractROIs(session_path, subject)

    # since this depends on finding the preSRS session first and setting PreSRSSequences, iterate through the
    # sessions again a second time but this time finding the post 3SRS session
    for sess in fw_subject.sessions.iter():
        if post3moSessionDate in sess.label:  # Go through the 3month-postSRS session and retrieve the sequences
            # create session path
            session_path = os.path.join(subject_path, sess.label)[:-9]
            if not os.path.isdir(session_path):
                os.mkdir(session_path)

            # download and retrieve sequences
            (T1StealthBravo, T1CubeVasc, T2CubeFlair) = downloadSequences(sess, Post3MoSRSRegfiles, subject,
                                                                          session_path)
            if T1StealthBravo:  # perform registration on these files if present
                registration(PreT1StealthBravo, T1StealthBravo, post3mo_treat_acquisition, subject, 'Post3Mo',
                             'T1StealthBravo')
            if T1CubeVasc:
                registration(PreT1StealthBravo, T1CubeVasc, post3mo_treat_acquisition, subject, 'Post3Mo',
                             'T1CubeVasc')
            if T2CubeFlair:
                registration(PreT1StealthBravo, T2CubeFlair, post3mo_treat_acquisition, subject, 'Post3Mo',
                                 'T2CubeFlair')

    if not CT_path or not ROIs_path:  # if there are no rois, then continue
        continue

    # Transform from CT to MRI image space
    CT_output_path = os.path.join(nifti_path, '{}_regCT.nii'.format(subject))
    if not os.path.exists(CT_output_path):
        MRI = ants.image_read(PreT1StealthBravo)  # read the T1StealthBravo
        CT_in = ants.image_read(CT_path)  # read the CT and set air = 0
        CT_in = CT_in + 1000
        CT_in[CT_in < 0] = 0

        # register
        regCTtoMRI = ants.registration(fixed=MRI, moving=CT_in, type_of_transform='Similarity')

        # fix CT back to HU
        CT_out = regCTtoMRI['warpedmovout']
        CT_out = CT_out - 1000

        # Save and upload registered CT image to flywheel
        ants.image_write(regCTtoMRI['warpedmovout'], CT_output_path)
    else:
        print('{} already exists'.format(CT_output_path))
    upload_file_to_acquisition(pre_treat_acquisition, CT_output_path)

    # Apply that transformation onto each of the ROIs, thus fusing the RT structs onto the MRI
    for roi in ROIs_path:
        roi_output_path = '{}_Reg.nii'.format(roi[:-4])
        if not os.path.exists(roi_output_path):
            rtstruct = ants.image_read(roi)
            # use genericlabel as interpolator since rtstruct mask is binary
            RTStructReg = ants.apply_transforms(fixed=MRI, moving=rtstruct, transformlist=regCTtoMRI['fwdtransforms'],
                                                interpolator='genericLabel')
            # Save and upload registered ROI image to flywheel
            ants.image_write(RTStructReg, roi_output_path)
        else:
            print('{} already exists'.format(roi_output_path))
        upload_file_to_acquisition(ext_ROI_acquisition, roi_output_path)
    fw_subject = fw_subject.reload()
    break
