import numpy as np
import tensorflow as tf
import keras
from keras.optimizers import Adam
import time
from keras.layers import Dense, concatenate, Convolution2D, Flatten
import os
from keras.callbacks import TensorBoard
import time
MODEL_NAME = "ddpg_"
from buffer_ddpg import ReplayBuffer
from keras.utils import plot_model
 
class Agent:

    """
    * init values for agent
    * set buffer and networks

    * gamma: is the discount factor
    * alpha: is the learning rate
    * epsilon: is the exploring rate
    """

    def __init__(self, input_dims, scaler_dims, alpha=0.001, beta=0.002, 
                 gamma=0.99, n_actions=2, max_size=50000, min_mem_size = 100,
                 tau=0.005, batch_size=64, noise=0.1, replace_target =100):
 
        self.gamma = gamma
        self.tau = tau
        self.n_actions = n_actions
        self.noise = noise
        self.batch_size = batch_size
        self.replace_target = replace_target

        #* Set up Buffer (NOT PER)
        self.memory = ReplayBuffer(max_size, min_mem_size, input_dims, n_actions, number_of_values= scaler_dims)

        #! [-1, +1] SET MANUEL
        self.max_action = 1.0
        self.min_action = -1.0
        
        #* Network set up for ACTOR-CRITIC and their target networks
        self.actor = ActorNetwork(n_actions=n_actions, observation_input_dims = input_dims, 
                                    scaler_input_shape=scaler_dims,name='actor')
        self.critic = CriticNetwork(observation_input_dims = input_dims, 
                                    scaler_input_shape=scaler_dims, name='critic')
        self.target_actor = ActorNetwork(n_actions=n_actions, observation_input_dims = input_dims, 
                                    scaler_input_shape=scaler_dims,
                                         name='target_actor')
        self.target_critic = CriticNetwork(observation_input_dims = input_dims, 
                                    scaler_input_shape=scaler_dims, name='target_critic')

        #***** COMPILE NETWORKS
        self.actor.compile(optimizer=Adam(learning_rate=alpha))
        self.critic.compile(optimizer=Adam(learning_rate=beta))
        self.target_actor.compile(optimizer=Adam(learning_rate=alpha))
        self.target_critic.compile(optimizer=Adam(learning_rate=beta))


        #!for later edit
        # self.tensorboard = ModifiedTensorBoard(log_dir=f"logs/{MODEL_NAME}-{int(time.time())}")

        self.update_network_parameters(tau=1)

    def update_network_parameters(self, tau=None):
        if tau is None:
            tau = self.tau

        weights = []
        targets = self.target_actor.weights
        for i, weight in enumerate(self.actor.weights):
            weights.append(weight * tau + targets[i]*(1-tau))
        self.target_actor.set_weights(weights)

        weights = []
        targets = self.target_critic.weights
        for i, weight in enumerate(self.critic.weights):
            weights.append(weight * tau + targets[i]*(1-tau))
        self.target_critic.set_weights(weights)

    #* Adds step's data to a memory replay array
    #* (observation space, action, reward, new observation space, done)    
    def remember(self, state, action, reward, new_state, done, info, new_info):
        self.memory.store_transition(state, action, reward, new_state, done, info, new_info)

    #* Saves weights only
    def save_models(self, actor_eval, actor_target, critic_eval, critic_target):

        self.actor.save_weights(actor_eval)
        self.target_actor.save_weights(actor_target)
        self.critic.save_weights(critic_eval)
        self.target_critic.save_weights(critic_target)

    def load_models(self, actor_eval, actor_target, critic_eval, critic_target):

        self.actor.load_weights(actor_eval)
        self.target_actor.load_weights(actor_target)
        self.critic.load_weights(critic_eval)
        self.target_critic.load_weights(critic_target)

    def choose_action(self, observation, scaler, evaluate=False):
        state = tf.convert_to_tensor([observation], dtype=tf.float32)
        scaler= tf.convert_to_tensor([scaler], dtype=tf.float32)

        actions = self.actor(state, scaler)
        #* adding noise
        if not evaluate:
            actions += tf.random.normal(shape=[self.n_actions],
                                        mean=0.0, stddev=self.noise)

        return actions[0]

    def learn(self):

        #* if memory size is smaller than min size, do nothing
        if self.memory.mem_cntr < self.memory.min_size:
            # print("MEMORY: ", self.memory.mem_cntr)
            return

        #* and ELSE:
        #* sample minibatch and get states vs..

        state, action, reward, new_state, done, info, new_info = \
            self.memory.sample_buffer(self.batch_size)

        state = state.reshape((self.batch_size, 64,64,1))
        new_state = new_state.reshape((self.batch_size, 64,64,1))

        #* Convert to tensors
        states = tf.convert_to_tensor(state, dtype=tf.float32)
        states_ = tf.convert_to_tensor(new_state, dtype=tf.float32)
        rewards = tf.convert_to_tensor(reward, dtype=tf.float32)
        actions = tf.convert_to_tensor(action, dtype=tf.float32)
        infos = tf.convert_to_tensor(info, dtype=tf.float32)
        infos_ = tf.convert_to_tensor(new_info, dtype=tf.float32)

        with tf.GradientTape() as tape:
            target_actions = self.target_actor(states_, infos)
            critic_value_ = tf.squeeze(self.target_critic(
                                states_, infos_, target_actions), 1)
            critic_value = tf.squeeze(self.critic(states, infos, actions), 1)
            target = rewards + self.gamma*critic_value_*(1-done)
            critic_loss = keras.losses.MSE(target, critic_value)

        critic_network_gradient = tape.gradient(critic_loss,
                                                self.critic.trainable_variables)
        self.critic.optimizer.apply_gradients(zip(
            critic_network_gradient, self.critic.trainable_variables))

        with tf.GradientTape() as tape:
            new_policy_actions = self.actor(states, infos)
            actor_loss = -self.critic(states, infos, new_policy_actions)
            actor_loss = tf.math.reduce_mean(actor_loss)

        actor_network_gradient = tape.gradient(actor_loss,
                                               self.actor.trainable_variables)
        self.actor.optimizer.apply_gradients(zip(
            actor_network_gradient, self.actor.trainable_variables))

        if self.memory.total_mem_cnt % self.replace_target == 0:

            self.update_network_parameters(self.tau)
            print("Target replaced")      


class CriticNetwork(keras.Model):

    def __init__(self, fc1_dims=512, fc2_dims=32, fc3_dims=4, observation_input_dims = 7,
            scaler_input_shape = None, n_actions = (2,), name='critic', chkpt_dir='./'):
        super(CriticNetwork, self).__init__()

        # self.image_input = keras.Input(shape=(observation_input_dims), name="img_input")
        # self.timeseries_input = keras.Input(shape=(scaler_input_shape), name="ts_input")

        self.n_actions = n_actions
        self.fc1_dims = fc1_dims
        self.fc2_dims = fc2_dims
        self.fc3_dims = fc3_dims

        #*image net
        # self.fc1 = Dense(self.fc1_dims, input_shape = observation_input_dims, activation='relu')
        self.fc1 = Convolution2D(32,8, activation='relu')
        self.fc1_ = Convolution2D(64,4, activation='relu')
        # self.fc1_ = Dense(self.fc1_dims, activation="relu")
        
        #* Flatten Layer
        self.flatten = Flatten()

        #*scaler net
        self.fc2 = Dense(self.fc2_dims, input_shape = scaler_input_shape,activation='relu')

        #* action net
        self.fc3 = Dense(self.fc3_dims, input_shape = self.n_actions, activation='relu')

        #* concatenate layer
        self.fc4 = Dense(512, activation="relu")
        # self.fc4_ = Dense(512, activation="relu")

        self.q = Dense(1, activation=None)

    def call(self, observation, scaler, action):

        #* Image Layer 2*256

        image_value = self.fc1(observation)
        image_value = self.fc1_(image_value)
        image_value = self.flatten(image_value)

        #* Vector Layer 1*64
        scaler_value = self.fc2(scaler)
        scaler_value = self.flatten(scaler_value)


        #* Action Layer 1*32
        action_value = self.fc3(action)
        action_value = self.flatten(action_value)

        #* Concatenate Layer 1*256
        x = concatenate([image_value,scaler_value,action_value])
        con_value = self.fc4(x)
        # con_value = self.fc4_(con_value)


        #* output q value 1
        q = self.q(con_value)

        return q

class ActorNetwork(keras.Model):

    def __init__(self, fc1_dims=512, fc2_dims=32, fc3_dims = 512, observation_input_dims = 7,
            scaler_input_shape = None, n_actions=2, name='actor',
            chkpt_dir='./'):
        super(ActorNetwork, self).__init__()

        # self.image_input = keras.Input(shape=(observation_input_dims), name="img_input")
        # self.timeseries_input = keras.Input(shape=(scaler_input_shape), name="ts_input")

        self.fc1_dims = fc1_dims
        self.fc2_dims = fc2_dims
        self.fc3_dims = fc3_dims
        self.n_actions = n_actions

        #* Image Network
        # self.fc1 = Dense(self.fc1_dims, input_shape = observation_input_dims, activation='relu')
        self.fc1 = Convolution2D(32,8, activation='relu')
        self.fc1_ = Convolution2D(64,4, activation='relu')

        #* Flatten Layer
        self.flatten = Flatten()

        #* Scaler Network
        self.fc2 = Dense(self.fc2_dims, input_shape= scaler_input_shape ,activation='relu')

        #* Concatenate layer
        self.fc3 = Dense(self.fc3_dims, activation='relu')
        # self.fc3_ = Dense(self.fc3_dims, activation='relu')

        #* Output Layer
        self.mu = Dense(self.n_actions, activation='tanh')

    def call(self, observation, scaler):

        #* Image Layer 2*256
        prob_a = self.fc1(observation)
        prob_a = self.fc1_(prob_a)
        prob_a = self.flatten(prob_a)
        #* Vector Layer 1*64
        prob_b = self.fc2(scaler)
        prob_b = self.flatten(prob_b)

        #* Concatenate Layer 1*256
        x = concatenate([prob_a, prob_b])
        x = self.fc3(x)
        # x = self.fc3_(x)

        #* output 2
        mu = self.mu(x)

        return mu
