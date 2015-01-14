'''
Created on 21/02/2013

@author: u76345
'''
import os
import sys
import logging
import re
import numpy
from datetime import datetime, time
from osgeo import gdal

from agdc.stacker import Stacker
from EOtools.utils import log_multiline

# Set top level standard output 
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(message)s')
console_handler.setFormatter(console_formatter)

logger = logging.getLogger(__name__)
if not logger.level:
    logger.setLevel(logging.DEBUG) # Default logging level for all modules
    logger.addHandler(console_handler)
          
# Creates derived datasets by getting masking all MOD09 datasets in a stack with RBQ500 data          
class RBQ500Stacker(Stacker):

    """ Subclass of Stacker
    Used to implement specific functionality to create stacks of derived datasets.
    """
    def derive_datasets(self, input_dataset_dict, stack_output_info, tile_type_info):
        assert type(input_dataset_dict) == dict, 'input_dataset_dict must be a dict'
        
        log_multiline(logger.debug, input_dataset_dict, 'input_dataset_dict', '\t')    
       
        # Figure out our input/output files
        MOD09_dataset_path = input_dataset_dict['MOD09']['tile_pathname']
        
        MOD09_dataset = gdal.Open(MOD09_dataset_path)
        assert MOD09_dataset, 'Unable to open dataset %s' % MOD09_dataset
        total_bands = MOD09_dataset.RasterCount
        logger.debug('Opened MOD09 dataset %s', MOD09_dataset_path)

        # Get the pixel mask as a single numpy array
        # Be mindful of memory usage, should be fine in this instance
        RBQ500_mask = self.get_pqa_mask(input_dataset_dict['RBQ500']['tile_pathname']) 
        
        # Instead of receiving one entry, this will have a numbpqer of entries = to the number of bands
        output_dataset_dict = {}
        
        # Instead of creating 1 file with many bands
        # Let's create many files with a single band
        for index in range(1, total_bands + 1):
        
            output_tile_path = os.path.join(self.output_dir, re.sub('\.\w+$', 
                                                                '_RBQ500_masked_band_%s%s' % (index, tile_type_info['file_extension']),
                                                                os.path.basename(MOD09_dataset_path)))
            output_stack_path = os.path.join(self.output_dir, 'RBQ500_masked_band_%s.vrt' % (index))
            
            # Copy metadata for eventual inclusion in stack file output
            # This could also be written to the output tile if required
            output_dataset_info = dict(input_dataset_dict['MOD09'])
            output_dataset_info['tile_pathname'] = output_tile_path # This is the most important modification - used to find 
            output_dataset_info['band_name'] = 'MOD09 band %s with RBQ500 mask applied' % (index)
            output_dataset_info['band_tag'] = 'MOD09-RBQ500-%s' % (index)
            output_dataset_info['tile_layer'] = 1

        
            # Create a new geotiff for the masked output
            gdal_driver = gdal.GetDriverByName(tile_type_info['file_format'])
            output_dataset = gdal_driver.Create(output_tile_path, 
                                            MOD09_dataset.RasterXSize, MOD09_dataset.RasterYSize,
                                            1, MOD09_dataset.GetRasterBand(index).DataType,
                                            tile_type_info['format_options'].split(','))
                                            
            assert output_dataset, 'Unable to open output dataset %s' % output_dataset                                   
            output_dataset.SetGeoTransform(MOD09_dataset.GetGeoTransform())
            output_dataset.SetProjection(MOD09_dataset.GetProjection()) 
        
            # Mask our band (each band is a numpy array of values)
            input_band = MOD09_dataset.GetRasterBand(index)
            input_band_data = input_band.ReadAsArray()
        
            # Apply the mask in place on input_band_data
            no_data_value = -32767
            self.apply_pqa_mask(input_band_data, RBQ500_mask, no_data_value)
        
            # Write the data as a new band
            output_band = output_dataset.GetRasterBand(1)
            output_band.WriteArray(input_band_data)
            output_band.SetNoDataValue(no_data_value)
            output_band.FlushCache()
            
            # This is not strictly necessary - copy metadata to output dataset
            output_dataset_metadata = MOD09_dataset.GetMetadata()
            if output_dataset_metadata:
                output_dataset.SetMetadata(output_dataset_metadata) 
        
            output_dataset.FlushCache()
            logger.info('Finished writing %s', output_tile_path)
        
            output_dataset_dict[output_stack_path] = output_dataset_info

        log_multiline(logger.debug, output_dataset_dict, 'output_dataset_dict', '\t')    
        
        return output_dataset_dict
    
# This is the main function when this script is directly executed - You can mostly
# ignore it's contents. The bulk of the "interesting work" is in the above class
if __name__ == '__main__':
    def date2datetime(input_date, time_offset=time.min):
        if not input_date:
            return None
        return datetime.combine(input_date, time_offset)
    
    # Stacker class takes care of command line parameters
    stacker = RBQ500Stacker()
    
    if stacker.debug:
        console_handler.setLevel(logging.DEBUG)
    
    # Check for required command line parameters
    assert (stacker.x_index and stacker.y_index), 'You must specify Tile X/Y-index (-x/-y or --x_index/--y_index)'
    assert stacker.output_dir, 'Output directory not specified (-o or --output)'
    
    
    stack_info_dict = stacker.stack_derived(x_index=stacker.x_index, 
                         y_index=stacker.y_index, 
                         stack_output_dir=stacker.output_dir, 
                         start_datetime=date2datetime(stacker.start_date, time.min), 
                         end_datetime=date2datetime(stacker.end_date, time.max), 
                         satellite=stacker.satellite, 
                         sensor=stacker.sensor)
    
    log_multiline(logger.debug, stack_info_dict, 'stack_info_dict', '\t')
    logger.info('Finished creating %d temporal stack files in %s.', len(stack_info_dict), stacker.output_dir)
