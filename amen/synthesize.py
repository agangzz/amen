#!/usr/bin/env python
# -*- coding: utf-8 -*-

import types
import librosa
import pandas as pd
import numpy as np
from scipy.sparse import lil_matrix
from amen.audio import Audio
from amen.time import TimingList
from amen.exceptions import SynthesizeError

def _format_inputs(inputs):
    """
    Organizes inputs to be a list of (TimeSlice, start_time) tuples, 
    if they are not already of that form.
    # We may want to update this to support "properly" zipped lists of tuples.

    Acceptable forms are:
        - A list of TimeSlices - the TimeSlices will be concatenated.
        - A generator that returns (TimeSlice, start_time).
        - A tuple of (TimeSlices, start_times).
    """
    formatted_list = []
    if isinstance(inputs, list):
        time_index = pd.to_timedelta(0.0, 's')
        timings = []
        for time_slice in inputs:
            timings.append(time_index)
            time_index = time_index + time_slice.duration
        formatted_list = zip(inputs, timings)
    elif isinstance(inputs, tuple):
        formatted_list = zip(inputs[0], inputs[1])
    elif isinstance(inputs, types.GeneratorType):
        formatted_list = inputs
    return formatted_list

def synthesize(inputs):
    """
    Generate new Audio objects for output or further remixing.

    Parameters
    ----------

    inputs: generator, list, or tuple.
        See _format_inputs for details on parsing inputs.

    Returns
    ------
    An Audio object
    """
    # First we organize our inputs.
    inputs = _format_inputs(inputs)

    max_time = 0.0
    sample_rate = 44100
    array_length = 20 * 60 # 20 minutes!
    array_shape = (2, sample_rate * array_length)
    sparse_array = lil_matrix(array_shape)

    initial_offset = 0
    for i, (time_slice, start_time) in enumerate(inputs):
        # get the actual, zero-corrected audio and the offsets
        resampled_audio, left_offsets, right_offsets = time_slice.get_samples()

        # set the initial offset, so we don't miss the start of the array
        if i == 0:
            initial_offset = max(left_offsets[0] * -1, right_offsets[0] * -1)

        # get the target start and duration
        start_time = start_time.delta * 1e-9
        duration = time_slice.duration.delta * 1e-9

        # find the max time
        if start_time + duration > max_time:
            max_time = start_time + duration
        # error if we'd go too far
        if start_time + duration > array_length:
            raise SynthesizeError("Amen can only synthesize up to 20 minutes of audio.")

        # get the target start and end samples
        starting_sample, ending_sample = librosa.time_to_samples([start_time, start_time + duration], sr=time_slice.audio.sample_rate)

        # figure out the actual starting and ending samples for each channel
        left_start = starting_sample + left_offsets[0] + initial_offset
        left_end = ending_sample + left_offsets[1] + initial_offset
        right_start = starting_sample + right_offsets[0] + initial_offset
        right_end = ending_sample + right_offsets[1] + initial_offset

        # add the data from each channel to the array
        sparse_array[0, left_start:left_end] += resampled_audio[0]
        sparse_array[1, right_start:right_end] += resampled_audio[1]

    max_samples = librosa.time_to_samples([max_time], sr=sample_rate)
    truncated_array = sparse_array[:, 0:max_samples].toarray()
    output = Audio(raw_samples=truncated_array)
    return output
