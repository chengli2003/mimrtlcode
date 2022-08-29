import collections
import csv
import logging
import os

import SimpleITK as sitk

import radiomics
from radiomics import featureextractor

# initialize the file paths to hold all the images separated by sequence and SRS Date
root = '/shares/mimrtl/Users/Chengnan/SRS_Immunotherapy'
PreT1Bravo_path = os.path.join(root, 'PreT1Bravo_Immuno');
PreT1Vasc_path = os.path.join(root, 'PreT1Vasc_Immuno');
PreT2Flair_path = os.path.join(root, 'PreT2Flair_Immuno');
Post3MoT1Bravo_path = os.path.join(root, 'Post3MoT1Bravo_Immuno');
Post3MoT1Vasc_path = os.path.join(root, 'Post3MoT1Vasc_Immuno');
Post3MoT2Flair_path = os.path.join(root, 'Post3MoT2Flair_Immuno');

def runRadiomics(outPath, batchFile, params):
    """Runs radiomics on the batchFile with the given settings

    Args:
        outPath: base path to hold all the input and output files
        batchFile: name of batchFile csv
        params: path for params file (if it exists)
    """

    # initializing the input path, output path, and logging path
    inputCSV = os.path.join(outPath, batchFile)
    outputFilepath = os.path.join(outPath, 'radiomics_features.csv')
    if os.path.exists(outputFilepath): # remove and restart outputFilepath
        os.remove(outputFilepath)
    progress_filename = os.path.join(outPath, 'pyrad_log.txt')

    # Configure logging
    rLogger = logging.getLogger('radiomics')

    # Set logging level
    # rLogger.setLevel(logging.INFO)  # Not needed, default log level of logger is INFO

    # Create handler for writing to log file
    handler = logging.FileHandler(filename=progress_filename, mode='w')
    handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s: %(message)s'))
    rLogger.addHandler(handler)

    # Initialize logging for batch log messages
    logger = rLogger.getChild('batch')

    # Set verbosity level for output to stderr (default level = WARNING)
    radiomics.setVerbosity(logging.INFO)

    logger.info('pyradiomics version: %s', radiomics.__version__)
    logger.info('Loading CSV')

    flists = []
    try: # store CSV input
        with open(inputCSV, 'r') as inFile:
            cr = csv.DictReader(inFile, lineterminator='\n')
            flists = [row for row in cr]
    except Exception:
        logger.error('CSV READ FAILED', exc_info=True)

    logger.info('Loading Done')
    logger.info('Patients: %d', len(flists))

    if os.path.isfile(params):
        extractor = featureextractor.RadiomicsFeatureExtractor(params)
    else:  # Parameter file not found, use hardcoded settings instead
        settings = {}
        settings['binWidth'] = 25
        settings['resampledPixelSpacing'] = None  # [3,3,3]
        settings['interpolator'] = sitk.sitkBSpline
        settings['enableCExtensions'] = True

        extractor = featureextractor.RadiomicsFeatureExtractor(**settings)
        # extractor.enableInputImages(wavelet= {'level': 2})

    logger.info('Enabled input images types: %s', extractor.enabledImagetypes)
    logger.info('Enabled features: %s', extractor.enabledFeatures)
    logger.info('Current settings: %s', extractor.settings)

    headers = None

    for idx, entry in enumerate(flists, start=1): # iterate through each row of CSV
        logger.info("(%d/%d) Processing Patient (Image: %s, Mask: %s)", idx, len(flists), entry['Image'], entry['Mask'])

        imageFilepath = entry['Image']
        maskFilepath = entry['Mask']
        label = entry.get('Label', None)

        if str(label).isdigit():
            label = int(label)
        else:
            label = None

        if (imageFilepath is not None) and (maskFilepath is not None):
            featureVector = collections.OrderedDict(entry)
            # first two columns are the image and mask file paths
            featureVector['Image'] = os.path.basename(imageFilepath)
            featureVector['Mask'] = os.path.basename(maskFilepath)

            try: # update additional columns with extracted features
                featureVector.update(extractor.execute(imageFilepath, maskFilepath, label))
                with open(outputFilepath, 'a') as outputFile:
                    writer = csv.writer(outputFile, lineterminator='\n')
                    if headers is None: # write column headers as first line
                        headers = list(featureVector.keys())
                        writer.writerow(headers)

                    row = []
                    for h in headers:
                        row.append(featureVector.get(h, "N/A"))
                    writer.writerow(row)
            except Exception:
                logger.error('FEATURE EXTRACTION FAILED', exc_info=True)

# Run radiomics for all the sequences and for all the SRS Statuses
runRadiomics(PreT1Bravo_path, 'PreT1Bravo_batchFile.csv', os.path.join(root, 'Params.yaml'))
runRadiomics(PreT1Vasc_path, 'PreT1Vasc_batchFile.csv', os.path.join(root, 'Params.yaml'))
runRadiomics(PreT2Flair_path, 'PreT2Flair_batchFile.csv', os.path.join(root, 'Params.yaml'))
runRadiomics(Post3MoT1Bravo_path, 'Post3MoT1Bravo_batchFile.csv', os.path.join(root, 'Params.yaml'))
runRadiomics(Post3MoT1Vasc_path, 'Post3MoT1Vasc_batchFile.csv', os.path.join(root, 'Params.yaml'))
runRadiomics(Post3MoT2Flair_path, 'Post3MoT2Flair_batchFile.csv', os.path.join(root, 'Params.yaml'))
