import os
import logging
from deepviz_webui.utils.decaf import load_from_convnet
import cPickle as pickle
from itertools import izip
import numpy as np
from multiprocessing import Pool
import time


_log = logging.getLogger("ModelStatsDB")
_shared_data = None


def _process_model(x):
    (timestep, model_filename) = x
    (directory, image_data, image_classes, num_classes) = _shared_data
    _log.info("Processing model for timestep %i" % timestep)
    model = load_from_convnet(model_filename)
    stats = ModelStats.create(model, image_data, image_classes, num_classes)
    stats.save(os.path.join(directory, str(timestep)))


class ModelStatsDB(object):
    """
    Persistent database of model statistics.
    """
    def __init__(self, directory):
        self._directory = directory
        self._stats = {}

    def get_stats(self, timestep):
        if timestep not in self._stats:
            stats_filename = os.path.join(self._directory, str(timestep))
            if not os.path.isfile(stats_filename):
                raise ValueError("Don't have statistics for timestep %i" % timestep)
            else:
                self._stats[timestep] = ModelStats.load(stats_filename)
        return self._stats[timestep]

    @classmethod
    def create(cls, directory, model_filenames, image_data, image_classes, num_classes):
        """
        Warning: this `create` method is not threadsafe!
        """
        global _shared_data
        _shared_data = (directory, image_data, image_classes, num_classes)
        pool = Pool(4)  # TODO: make pool size configurable
        pool.map(_process_model, enumerate(model_filenames), 1)
        _shared_data = None
        return ModelStatsDB(directory)


class ModelStats(object):
    """
    Provides access to statistics gathered while applying a model
    to an image corpus.
    """

    def __init__(self, confusion_matrix):
        self._confusion_matrix = confusion_matrix

    @property
    def confusion_matrix(self):
        """
        Return a confusion matrix, where entry `C[i, j]` gives the number
        of images of true class `i` that were classified as class `j`.
        """
        return self._confusion_matrix

    @classmethod
    def load(cls, filename):
        with open(filename) as f:
            return pickle.load(f)

    def save(self, filename):
        """
        Persist the database to a file.
        """
        with open(filename, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def create(cls, model, image_data, image_classes, num_classes):
        """
        Create a new ModelStatsDatabase by applying a trained model
        to a collection of images.
        """
        BATCH_SIZE = 1000
        image_data = image_data.astype(np.float32)
        confusion_matrix = np.zeros((num_classes, num_classes))
        for chunk_start in xrange(0, len(image_data), BATCH_SIZE):
            images = image_data[chunk_start:chunk_start + BATCH_SIZE]
            true_classes = image_classes[chunk_start:chunk_start + BATCH_SIZE]
            start_time = time.time()
            outputs = model.predict(data=images, output_blobs=["probs_cudanet_out"])
            end_time = time.time()
            _log.info("Processed batch of %i images in %f seconds" %
                     (len(images), end_time - start_time))
            predicted_classes = (np.argmax(x) for x in outputs["probs_cudanet_out"])
            for (true_class, predicted_class) in izip(true_classes, predicted_classes):
                confusion_matrix[true_class][predicted_class] += 1
        return ModelStats(confusion_matrix)