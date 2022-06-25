# Copyright 2022 The KerasCV Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import warnings

import tensorflow as tf

from keras_cv import core
from keras_cv.layers.preprocessing.base_image_augmentation_layer import (
    BaseImageAugmentationLayer, )
from keras_cv.utils import preprocessing


@tf.keras.utils.register_keras_serializable(package="keras_cv")
class RandomResizedCrop(BaseImageAugmentationLayer):
    """Randomly crops a part of an image and resizes it to provided size.

    This implementation takes an intuitive approach, where we crop the images to a
    random height and width, and then resize them. To do this, we first sample a
    random value for area using `area_factor` and a value for aspect ratio using
    `aspect_ratio_factor`. Further we get the new height and width by
    dividing and multiplying the old height and width by the random area
    respectively. We then sample offsets for height and width and clip them such
    that the cropped area does not exceed image boundaries. Finally we do the
    actual cropping operation and resize the image to `target_size`.

    Args:
        target_size: A tuple of two integers used as the target size to ultimately crop
            images to.
        area_factor: (Optional) A tuple of two floats, a single float or
            `keras_cv.FactorSampler`. The ratio of area of the cropped part to
            that of original image is sampled using this factor. Represents the
            lower and upper bounds for the area relative to the original image
            of the cropped image before resizing it to `target_size`.
            `target_size`.  Defaults to (0.08, 1.0).
        aspect_ratio_factor: (Optional) A tuple of two floats, a single float or
            `keras_cv.FactorSampler`. Aspect ratio means the ratio of width to
            height of the cropped image. In the context of this layer, the aspect ratio
            sampled represents a value to distort the aspect ratio by.
            Represents the lower and upper bound for the aspect ratio of the
            cropped image before resizing it to `target_size`. Defaults to
            (3./4., 4./3.).
        interpolation: (Optional) A string specifying the sampling method for
            resizing. Defaults to "bilinear".
        seed: (Optional) Used to create a random seed. Defaults to None.
    """
    def __init__(
        self,
        target_size,
        area_factor=(0.08, 1.0),
        aspect_ratio_factor=(3. / 4., 4. / 3.),
        interpolation="bilinear",
        seed=None,
        **kwargs,
    ):
        super().__init__(seed=seed, **kwargs)

        self.target_size = target_size

        aspect_ratio_factor = aspect_ratio_factor or (3. / 4., 4. / 3.)
        if isinstance(aspect_ratio_factor, tuple):
            min_aspect_ratio = min(aspect_ratio_factor)
            max_aspect_ratio = max(aspect_ratio_factor)
        elif isinstance(aspect_ratio_factor, core.FactorSampler):
            pass
        else:
            raise ValueError(
                "Expected `aspect_ratio` to be tuple or FactorSampler. Received "
                f"RandomResizedCrop(aspect_ratio_factor={aspect_ratio_factor})."
            )

        self.aspect_ratio_factor = preprocessing.parse_factor(
            aspect_ratio_factor,
            min_value=min_aspect_ratio,
            max_value=max_aspect_ratio,
            param_name="aspect_ratio_factor",
            seed=seed,
        )
        self.area_factor = preprocessing.parse_factor(
            area_factor,
            max_value=1.0,
            param_name="area_factor",
            seed=seed,
        )

        self.interpolation = interpolation
        self.seed = seed

        if area_factor == 0.0 and aspect_ratio_factor == 0.0:
            warnings.warn(
                "RandomResizedCrop received both `area_factor=0.0` and "
                "`aspect_ratio_factor=0.0`. As a result, the layer will perform no "
                "augmentation.")

    def get_random_transformation(self,
                                  image=None,
                                  label=None,
                                  bounding_box=None,
                                  **kwargs):
        area_factor = self.area_factor()
        aspect_ratio = self.aspect_ratio_factor()

        new_height = tf.clip_by_value(
            tf.sqrt(area_factor / aspect_ratio), 0.0,
            1.0)  # to avoid unwanted/unintuitive effects
        new_width = tf.clip_by_value(tf.sqrt(area_factor * aspect_ratio), 0.0,
                                     1.0)

        height_offset = self._random_generator.random_uniform(
            (),
            minval=tf.minimum(0.0, 1.0 - new_height),
            maxval=tf.maximum(0.0, 1.0 - new_height),
            dtype=tf.float32,
        )

        width_offset = self._random_generator.random_uniform(
            (),
            minval=tf.minimum(0.0, 1.0 - new_width),
            maxval=tf.maximum(0.0, 1.0 - new_width),
            dtype=tf.float32,
        )

        y1 = height_offset
        y2 = height_offset + new_height
        x1 = width_offset
        x2 = width_offset + new_width

        return [[y1, x1, y2, x2]]

    def call(self, inputs, training=True):

        if training:
            return super().call(inputs, training)
        else:
            inputs = self._ensure_inputs_are_compute_dtype(inputs)
            inputs, is_dict, use_targets = self._format_inputs(inputs)
            output = inputs
            # self._resize() returns valid results for both batched and
            # unbatched
            output["images"] = self._resize(inputs["images"])
            return self._format_output(output, is_dict, use_targets)

    def augment_image(self, image, transformation, **kwargs):
        image = tf.expand_dims(image, axis=0)
        boxes = transformation

        # See bit.ly/tf_crop_resize for more details
        augmented_image = tf.image.crop_and_resize(
            image,  # image shape: [B, H, W, C]
            boxes,  # boxes: (1, 4) in this case; represents area
            # to be cropped from the original image
            [0],  # box_indices: maps boxes to images along batch axis
            # [0] since there is only one image
            self.target_size,  # output size
        )

        return tf.squeeze(augmented_image, axis=0)

    def _resize(self, image):
        outputs = tf.keras.preprocessing.image.smart_resize(
            image, self.target_size)
        # smart_resize will always output float32, so we need to re-cast.
        return tf.cast(outputs, self.compute_dtype)

    def get_config(self):
        config = super().get_config()
        config.update({
            "target_size": self.target_size,
            "area_factor": self.area_factor,
            "aspect_ratio_factor": self.aspect_ratio_factor,
            "interpolation": self.interpolation,
            "seed": self.seed,
        })
        return config
