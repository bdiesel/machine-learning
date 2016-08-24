from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import time
import numpy as np
import sys
import os
import tensorflow as tf

from svhn_data import load_svhn_data
from datetime import datetime
from svhn_model import classification_head
from pdb import set_trace as bp

TENSORBOARD_SUMMARIES_DIR = '/tmp/svhn_classifier_logs'
NUM_LABELS = 10
IMG_ROWS = 32
IMG_COLS = 32
NUM_CHANNELS = 3
SAVE_FILE = "classifier.ckpt"

BATCH_SIZE = 256
NUM_EPOCHS = 100

# LEARING RATE HYPER PARAMS
LEARN_RATE = 0.05
DECAY_RATE = 0.975


def error_rate(predictions, labels):
    correct_prediction = tf.equal(tf.argmax(
                                  predictions, 1), tf.argmax(labels, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
    return accuracy.eval() * 100


def prepare_log_dir():
    '''Clears the log files then creates new directories to place
        the tensorbard log file.'''
    if tf.gfile.Exists(TENSORBOARD_SUMMARIES_DIR):
        tf.gfile.DeleteRecursively(TENSORBOARD_SUMMARIES_DIR)
    tf.gfile.MakeDirs(TENSORBOARD_SUMMARIES_DIR)


def fill_feed_dict(data, labels, x, y_, step):
    size = labels.shape[0]
    # Compute the offset of the current minibatch in the data.
    # Note that we could use better randomization across epochs.
    offset = (step * BATCH_SIZE) % (size - BATCH_SIZE)
    batch_data = data[offset:(offset + BATCH_SIZE), ...]
    batch_labels = labels[offset:(offset + BATCH_SIZE)]
    return {x: batch_data, y_: batch_labels}


def train_classification(train_data, train_labels, valid_data, valid_labels,
                         test_data, test_labels, train_size, saved_weights_path):
    global_step = tf.Variable(0, trainable=False)

    # This is where training samples and labels are fed to the graph.
    with tf.name_scope('input'):
        X_train = tf.placeholder(tf.float32, shape=[BATCH_SIZE, IMG_ROWS, IMG_COLS, NUM_CHANNELS])
        X_valid = tf.constant(valid_data)
        X_test = tf.constant(test_data)

    with tf.name_scope('image'):
        tf.image_summary('train_input', X_train, 10)
        tf.image_summary('valid_input', X_valid, 10)
        tf.image_summary('test_input', X_test, 10)

    y_ = tf.placeholder(tf.float32, shape=[BATCH_SIZE, NUM_LABELS])

    # Training computation: logits + cross-entropy loss.
    logits = classification_head(X_train, True)
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits, y_))

    learning_rate = tf.train.exponential_decay(LEARN_RATE, global_step*BATCH_SIZE, train_size, DECAY_RATE, staircase=True)
    tf.scalar_summary('learning_rate', learning_rate)
    '''Optimizer: set up a variable that's incremented
      once per batch and controls the learning rate decay.'''
    optimizer = tf.train.AdagradOptimizer(learning_rate).minimize(loss, global_step=global_step)

    # Predictions for the training, validation, and test data.
    train_prediction = tf.nn.softmax(classification_head(X_train))
    valid_prediction = tf.nn.softmax(classification_head(X_valid))
    test_prediction = tf.nn.softmax(classification_head(X_test))

    init_op = tf.initialize_all_variables()

    # Accuracy ops to save and restore all the variables.
    saver = tf.train.Saver()

    # Create a local session to run the training.
    start_time = time.time()
    with tf.Session(config=tf.ConfigProto(log_device_placement=False)) as sess:

        # Restore variables from disk.
        if(saved_weights_path):
            saver.restore(sess, saved_weights_path)
            print("Model restored.")

        sess.run(init_op)
        # Run all the initializers to prepare the trainable parameters.

        # Add histograms for trainable variables.
        for var in tf.trainable_variables():
            tf.histogram_summary(var.op.name, var)

        # Add accuracy to tesnosrboard
        with tf.name_scope('accuracy'):
            with tf.name_scope('correct_prediction'):
                correct_prediction = tf.equal(tf.argmax(logits, 1), tf.argmax(y_, 1))
            with tf.name_scope('accuracy'):
                accuracy = tf.reduce_mean(tf.cast(correct_prediction,  tf.int64))
            tf.scalar_summary('accuracy', accuracy)

        # Prepare vairables for the tensorboard
        merged = tf.merge_all_summaries()

        train_writer = tf.train.SummaryWriter(TENSORBOARD_SUMMARIES_DIR + '/train', sess.graph)
        # valid_writer = tf.train.SummaryWriter(TENSORBOARD_SUMMARIES_DIR + '/validation')
        # test_writer = tf.train.SummaryWriter(TENSORBOARD_SUMMARIES_DIR + '/test')

        run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
        run_metadata = tf.RunMetadata()

        # Loop through training steps.
        for step in xrange(int(NUM_EPOCHS * train_size) // BATCH_SIZE):
            # Run the graph and fetch some of the nodes.
            # This dictionary maps the batch data (as a numpy array) to the
            feed_dict = fill_feed_dict(train_data, train_labels, X_train, y_, step)
            _, l, lr, preds = sess.run([optimizer, loss, learning_rate, train_prediction], feed_dict=feed_dict)
            duration = time.time() - start_time

            if step % 1000 == 0:
                # valid_feed_dict = fill_feed_dict(valid_data, valid_labels, X_valid, y_, step)
                # valid_summary, _, l, lr, valid_predictions = sess.run([merged, optimizer, loss, learning_rate, valid_prediction], feed_dict=valid_feed_dict, options=run_options, run_metadata=run_metadata)
                # valid_writer.add_run_metadata(run_metadata, 'step%03d' % step)
                # valid_writer.add_summary(valid_summary, step)

                train_summary, _, l, lr, predictions = sess.run([merged, optimizer, loss, learning_rate, train_prediction], feed_dict=feed_dict)
                train_writer.add_run_metadata(run_metadata, 'step%03d' % step)
                train_writer.add_summary(train_summary, step)

                print('Adding run metadata for', step)
                print('Validation Accuracy: %.2f%%' % error_rate(valid_prediction.eval(), valid_labels))

            if step % 100 == 0:
                elapsed_time = time.time() - start_time
                start_time = time.time()
                examples_per_sec = BATCH_SIZE / duration
                format_str = ('%s: step %d, loss = %.2f  learning rate = %.6f  (%.1f examples/sec; %.2f ''sec/batch)')
                print (format_str % (datetime.now(), step, l, lr, examples_per_sec, duration))
                train_error_rate = error_rate(preds, feed_dict[y_])
                print('Mini-Batch Accuracy: %.2f%%' % train_error_rate)
                sys.stdout.flush()

        # Save the variables to disk.
        save_path = saver.save(sess, SAVE_FILE)
        print("Model saved in file: %s" % save_path)
        print('Test Accuracy: %.2f%%' % error_rate(test_prediction.eval(), test_labels))
        train_writer.close()

        # test_feed_dict = fill_feed_dict(test_data, test_labels, X, y_, step)
        # _, l, lr, test_predictions = sess.run([optimizer, loss, learning_rate, prediction], feed_dict=test_feed_dict, options=run_options, run_metadata=run_metadata)
        # test_summary, _, l, lr, test_predictions = sess.run([merged, optimizer, loss, learning_rate, prediction], feed_dict=test_feed_dict, options=run_options, run_metadata=run_metadata)
        # test_writer.add_run_metadata(run_metadata, 'step%03d' % step)
        # test_writer.add_summary(test_summary, step)
        # test_error_rate = error_rate(test_predictions, test_feed_dict[y_])
        # print('Test Accuracy: %.2f%%' % test_error_rate)

        # valid_writer.close()
        # test_writer.close()


def main(saved_weights_path):
    prepare_log_dir()
    train_data, train_labels = load_svhn_data("train", "cropped")
    valid_data, valid_labels = load_svhn_data("valid", "cropped")
    test_data, test_labels = load_svhn_data("test", "cropped")

    test_dataX = test_data[0:3000]
    test_labelsX = test_labels[0:3000]

    print("Training", train_data.shape)
    print("Valid", valid_data.shape)
    print("Test", test_dataX.shape)

    train_size = train_labels.shape[0]
    saved_weights_path = None
    train_classification(train_data, train_labels, valid_data, valid_labels,
                         test_dataX, test_labelsX, train_size, saved_weights_path)


if __name__ == '__main__':
    saved_weights_path = None
    if len(sys.argv) > 1:
        print("Loading Saved Checkpoints From:", sys.argv[1])
        if os.path.isfile(sys.argv[1]):
            saved_weights_path = sys.argv[1]
        else:
            raise EnvironmentError("The weights file cannot be opened.")
    else:
        print("Starting without Saved Weights.")
    main(saved_weights_path)
