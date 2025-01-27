import tensorflow as tf
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt

##############################
# Standard TFRecord feature generation from https://www.tensorflow.org/tutorials/load_data/tfrecord.
def _bytes_feature_list(value):
  if isinstance(value,type(tf.constant(0))):
    value = value.numpy()
  if not isinstance(value, list):
    value = [value]
  return tf.train.Feature(bytes_list=tf.train.BytesList(value=value))

##############################
# Write trajectory dataset to tfrecord format.
def write_tfrecord(file_prefix,           # where to save the tfrecord without the extension
	               dataset,               # list of dataset entries to write
	               data_dict_function,    # function to convert entry to a dictionary
	               shuffle = False,       # whether to shuffle the data_list before writing
	               shuffle_seed = 0,      # set a random seed for deterministic shuffling
	               max_per_record = None, # whether to impose a max constraint on items per record
	               ):

	# Remove the suffix if given in the file_prefix string.
	if '.record' in file_prefix:
		file_prefix = file_prefix.split('.record')[0]
	if '.tfrecord' in file_prefix:
		file_prefix = file_prefix.split('.tfrecord')[0]

	# Shuffle the dataset if required with a specified seed.
	if shuffle:
		np.random.seed(shuffle_seed)
		np.random.shuffle(dataset)
	num_elements = len(dataset)

	# Handle case where there are a max number of items per record.
	# Else just write all items to one record.
	if max_per_record:
		assert type(max_per_record) == int
	else:
		max_per_record = num_elements

	current_split = 0
	current_dataset_ind = 0
	total_entries_written = 0

	while current_dataset_ind < num_elements:
		record_file = '{}_{}.record'.format(file_prefix, current_split)
		writer = tf.io.TFRecordWriter(record_file)
		print('***Started writing to {} at dataset index {} of {}'.format(
			   record_file, current_dataset_ind, num_elements))

		for ind in tqdm(range(max_per_record)):
			data_dict = data_dict_function(dataset[current_dataset_ind])

			if data_dict is not None and len(data_dict.keys()) > 0:
				# We have a valid entry, let's write to the record.
				ftr = {}
				for key in ['instance', 'sample', 'type']:
					ftr[key] = _bytes_feature_list(tf.compat.as_bytes(data_dict[key]))

				for key in ['velocity', 'acceleration', 'yaw_rate']:
					ftr[key] = _bytes_feature_list( tf.io.serialize_tensor(np.float64(data_dict[key])) )

				for key in ['pose', 'past_poses_local', 'future_poses_local']:
					ftr[key] = _bytes_feature_list( tf.io.serialize_tensor(data_dict[key].astype(np.float64)) )
					ftr[key + '_shape'] = \
					    _bytes_feature_list( np.array(data_dict[key].shape, np.int32).tobytes() )

				for key in ['past_tms', 'future_tms']:
					ftr[key] = _bytes_feature_list( tf.io.serialize_tensor(data_dict[key].astype(np.float64)) )

				ftr['image']       = \
				    _bytes_feature_list( data_dict['image'].tobytes() )
				ftr['image_shape'] = \
				    _bytes_feature_list( np.array(data_dict['image'].shape, np.int32).tobytes() )

				example = tf.train.Example(features = tf.train.Features(feature=ftr))
				writer.write(example.SerializeToString())
				total_entries_written += 1
			else:
				# We did not write a valid entry so let's not increment ind (number written).
				# We still increment current_dataset_ind below to move on to the next dataset entry.
				ind -= 1

			current_dataset_ind += 1
			if current_dataset_ind == num_elements:
				break

		writer.close()
		current_split += 1

	print('Finished writing: {} splits, {} entries written out of {}'.format(
		   current_split, total_entries_written, num_elements))

##############################
# Parse a single TFRecord instance without augmentation.
def _parse_function(proto):
	ftr = {'instance'                 : tf.io.FixedLenFeature([], tf.string),
	       'sample'                   : tf.io.FixedLenFeature([], tf.string),
	       'type'                     : tf.io.FixedLenFeature([], tf.string),
	       'velocity'                 : tf.io.FixedLenFeature([], tf.string),
	       'acceleration'             : tf.io.FixedLenFeature([], tf.string),
	       'yaw_rate'                 : tf.io.FixedLenFeature([], tf.string),
	       'pose'                     : tf.io.FixedLenFeature([], tf.string),
	       'pose_shape'               : tf.io.FixedLenFeature([], tf.string),
	       'past_poses_local'         : tf.io.FixedLenFeature([], tf.string),
	       'past_poses_local_shape'   : tf.io.FixedLenFeature([], tf.string),
	       'past_tms'                 : tf.io.FixedLenFeature([], tf.string),
	       'future_tms'               : tf.io.FixedLenFeature([], tf.string),
	       'future_poses_local'       : tf.io.FixedLenFeature([], tf.string),
	       'future_poses_local_shape' : tf.io.FixedLenFeature([], tf.string),
	       'image'                    : tf.io.FixedLenFeature([], tf.string),
	       'image_shape'              : tf.io.FixedLenFeature([], tf.string)
	      }

	data_dict = {}

	parsed_features = tf.io.parse_single_example(proto, ftr)

	for key in ['instance', 'sample', 'type']:
		data_dict[key] = parsed_features[key]

	for key in ['velocity', 'acceleration', 'yaw_rate']:
		data_dict[key] = tf.reshape(tf.io.parse_tensor(parsed_features[key], out_type=tf.float64), (1,))

	for key in ['future_tms', 'past_tms']:
		data_dict[key] = tf.io.parse_tensor(parsed_features[key], out_type=tf.float64)

	for key in ['pose', 'past_poses_local', 'future_poses_local']:
		value   = tf.io.parse_tensor(parsed_features[key], out_type=tf.float64)
		shape = tf.io.decode_raw(parsed_features[key + '_shape'], tf.int32)
		data_dict[key] = tf.reshape(value, shape)

	image              = tf.io.decode_raw(parsed_features['image'], tf.uint8)
	image_shape        = tf.io.decode_raw(parsed_features['image_shape'], tf.int32)
	data_dict['image'] = tf.reshape(image, image_shape)

	return data_dict
##############################
# Parse a single TFRecord instance without augmentation and excluding the images.
def _parse_no_img_function(proto):
	ftr = {'instance'                 : tf.io.FixedLenFeature([], tf.string),
	       'sample'                   : tf.io.FixedLenFeature([], tf.string),
	       'type'                     : tf.io.FixedLenFeature([], tf.string),
	       'velocity'                 : tf.io.FixedLenFeature([], tf.string),
	       'acceleration'             : tf.io.FixedLenFeature([], tf.string),
	       'yaw_rate'                 : tf.io.FixedLenFeature([], tf.string),
	       'pose'                     : tf.io.FixedLenFeature([], tf.string),
	       'pose_shape'               : tf.io.FixedLenFeature([], tf.string),
	       'past_poses_local'         : tf.io.FixedLenFeature([], tf.string),
	       'past_poses_local_shape'   : tf.io.FixedLenFeature([], tf.string),
	       'past_tms'                 : tf.io.FixedLenFeature([], tf.string),
	       'future_tms'               : tf.io.FixedLenFeature([], tf.string),
	       'future_poses_local'       : tf.io.FixedLenFeature([], tf.string),
	       'future_poses_local_shape' : tf.io.FixedLenFeature([], tf.string),
	      }

	data_dict = {}

	parsed_features = tf.io.parse_single_example(proto, ftr)

	for key in ['instance', 'sample', 'type']:
		data_dict[key] = parsed_features[key]

	for key in ['velocity', 'acceleration', 'yaw_rate']:
		data_dict[key] = tf.reshape(tf.io.parse_tensor(parsed_features[key], out_type=tf.float64), (1,))

	for key in ['future_tms', 'past_tms']:
		data_dict[key] = tf.io.parse_tensor(parsed_features[key], out_type=tf.float64)

	for key in ['pose', 'past_poses_local', 'future_poses_local']:
		value   = tf.io.parse_tensor(parsed_features[key], out_type=tf.float64)
		shape = tf.io.decode_raw(parsed_features[key + '_shape'], tf.int32)
		data_dict[key] = tf.reshape(value, shape)

	return data_dict
##############################
"""
NOTE: I'm not sure which perturbations are fair to regularize without
changing the future motion.  For example, image cutout could mask a pedestrian
the vehicle is trying to stop for.  And motion noise would need to match
the rasterized image history, which is not done at the moment.  Hence, it makes
more sense to keep the raw features constant and perhaps add noise/regularization
after the prediction features have been computed through GaussianNoise/Dropout.

NOTE: we would need to install tensorflow_addons (tfa below) for using this.
      I left this out of the conda install for now.
"""
# Parse a single TFRecord instance with augmentation (for training).
# def _parse_aug_function(proto):
	# data_dict = _parse_function(proto)
	# mask_size = 50
	# rvs = tf.random.uniform(shape=[2])

	# if rvs[0] < 0.4:
	# 	data_dict['image'] = tfa.image.random_cutout(tf.expand_dims(data_dict['image'], 0), mask_size)[0]

	# if rvs[1] < 0.4:
	# 	vx  = data_dict['velocity']
	# 	vaug = vx + \
	# 	       tf.random.uniform(shape=[1], minval=-0.1, maxval=0.1, dtype=tf.float64)[0]
	# 	data_dict['velocity'] = vaug

	# 	# For simplicity, we will only make small perturbations to the initial velocity.
	# 	# The acceleration and yaw rate are related to this initial velocity and the
	# 	# perturbations can have a large impact on the augmented accel/yaw rate.
	# 	# Ignoring those effects but leaving code for reference.

	# 	# wz  = data_dict['yaw_rate']
	# 	# acc = data_dict['acceleration']
	# 	# vtarget = vx + acc * tf.constant(0.1, dtype=tf.float64)
	# 	# curv    = wz / tf.math.maximum(vx, tf.constant(1.0, dtype=tf.float64))
	# 	# aug_range = tf.math.maximum(tf.constant(1.0, dtype=tf.float64), \
	# 	# 	                        tf.math.abs(vx / tf.constant(5.0, dtype=tf.float64)))
	# 	# vaug = tf.nn.relu(vx + aug_range*tf.random.uniform(shape=[1], dtype=tf.float64)[0])
	# 	# aaug = (vtarget - vaug) / tf.constant(0.1, dtype=tf.float64)
	# 	# waug = curv * vaug
	# 	# data_dict['yaw_rate']     = waug
	# 	# data_dict['acceleration'] = aaug

	# return data_dict

##############################
# Utility function to read and visualize TFRecords.
def visualize_tfrecords(tfrecord_files, max_batches=None):
	plt.ion()

	dataset = tf.data.TFRecordDataset(tfrecord_files)
	dataset = dataset.map(_parse_function) # can see augmentations with _parse_aug_function.
	dataset = dataset.batch(2)

	f1 = plt.figure()
	f2 = plt.figure()
	plt.subplot(211); im1 = plt.imshow(np.zeros((500, 500, 3), dtype=np.uint8))
	plt.subplot(212); im2 = plt.imshow(np.zeros((500, 500, 3), dtype=np.uint8))

	for batch_ind, entry in enumerate(dataset):
		# This returns a dictionary which maps to a batch_size x data_shape tensor.

		if batch_ind == 0:
			for key in entry.keys():
				if 'image' in key:
					pass
				else:
					print(key, entry[key])
					print()

		plt.figure(f1.number)
		plt.plot(entry['future_poses_local'][0][:,0], entry['future_poses_local'][0][:,1])
		plt.plot(entry['future_poses_local'][1][:,0], entry['future_poses_local'][1][:,1])

		im1.set_data( entry['image'][0] )
		im2.set_data( entry['image'][1] )
		plt.draw(); plt.pause(0.01)

		if max_batches is not None and batch_ind == max_batches:
			break

	plt.ioff()
	plt.show()

##############################
# Utility function to test dataset shuffling pipeline.
def shuffle_test(tfrecord_files, batch_size=32):
	example_dict = {}

	files   = tf.data.Dataset.from_tensor_slices(tfrecord_files)
	files   = files.shuffle(buffer_size=len(tfrecord_files), reshuffle_each_iteration=True)
	dataset = files.interleave(lambda x: tf.data.TFRecordDataset(x),
		                       cycle_length=2, block_length=16)
	dataset = dataset.map(_parse_no_img_function)
	dataset = dataset.shuffle(10*batch_size, reshuffle_each_iteration=True)
	dataset = dataset.batch(batch_size)
	dataset = dataset.prefetch(2)

	# First epoch: populate dictionary with unique element ids.
	for batch_ind, entry in tqdm(enumerate(dataset)):
		instances  = [tf.compat.as_str(x) for x in entry['instance'].numpy()]
		samples    = [tf.compat.as_str(x) for x in entry['sample'].numpy()]
		entry_inds = (np.arange(batch_size) + batch_ind * batch_size).astype(np.int)

		for eind, inst, samp in zip(entry_inds, samples, instances):
			example_dict[f"{inst}_{samp}"] = [eind]

	# Later epochs: Determine element order in each epoch to check randomness of shuffling.
	for epoch in range(2):
		print(f"Epoch {epoch}")
		for batch_ind, entry in tqdm(enumerate(dataset)):
			instances  = [tf.compat.as_str(x) for x in entry['instance'].numpy()]
			samples    = [tf.compat.as_str(x) for x in entry['sample'].numpy()]
			entry_inds = (np.arange(batch_size) + batch_ind * batch_size).astype(np.int)

			for eind, inst, samp in zip(entry_inds, samples, instances):
				example_dict[f"{inst}_{samp}"].append( eind )

	ranges = [np.amax(example_dict[k]) - np.amin(example_dict[k]) for k in example_dict.keys()]
	stds   = [np.std(example_dict[k]) for k in example_dict.keys()]

	for metric_fn, metric in zip([np.amin, np.amax, np.mean], ['min', 'max', 'mean']):
		print(f"Shuffle {metric} range and std dev: {metric_fn(ranges)}, {metric_fn(stds)}")
