import random
import numpy as np


#* storing states, actions, rewards, new states, terminal
class ReplayBuffer(object):

    """
    * init the values
    * for DQN actions are discrete
    """
    def __init__(self, max_size, min_size, input_shape, n_actions, discrete=True):
        self.mem_size = max_size
        self.mem_cntr = 0
        self.mem_cntr_ = 0
        self.min_size = min_size
        self.discrete = discrete
        self.state_memory = np.zeros((self.mem_size, input_shape))
        self.new_state_memory = np.zeros((self.mem_size, input_shape))
        dtype = np.int8 if self.discrete else np.float32
        self.action_memory = np.zeros((self.mem_size, n_actions), dtype=dtype)
        self.reward_memory = np.zeros(self.mem_size)
        self.terminal_memory = np.zeros(self.mem_size, dtype=np.float32)
        self.priorities = np.zeros(self.mem_size, dtype=np.float32)

    def store_transition(self, state, action, reward, state_, done):


        if self.mem_size > self.mem_cntr:
            index = self.mem_cntr % self.mem_size
            self.mem_cntr += 1

        elif self.mem_size == self.mem_cntr:
            index = self.mem_cntr_ % self.mem_size
            self.mem_cntr_ +=1
            if self.mem_cntr_ == self.mem_cntr:
                self.mem_cntr_ = 0
                
        self.state_memory[index] = state
        self.new_state_memory[index] = state_

        #* store one hot encoding of actions, if appropriate
        if self.discrete:

            #* Create an zeros-array size of the number of actions
            actions = np.zeros(self.action_memory.shape[1])

            #* Make 1 the value of performed action
            actions[action] = 1.0

            #* Store in action memory
            self.action_memory[index] = actions
        else:
            self.action_memory[index] = action

        #* store reward and if it's terminal info 
        self.reward_memory[index] = reward


        #* we send inverse done info!!!
        self.terminal_memory[index] = 1 - done
        self.priorities[index] = max(np.float32(self.priorities.max()), 1.0)

    def get_probabilities(self, priority_scale):
        scaled_priorities = np.array(self.priorities) ** priority_scale
        sample_probabilities = scaled_priorities / sum(scaled_priorities)
        return sample_probabilities
        
    def get_importance(self, probabilities):
        importance = 1/(self.mem_cntr) * 1/probabilities
        importance_normalized = importance / max(importance)
        return importance_normalized

    def sample_buffer(self, batch_size, priority_scale=1.0):
        sample_size = batch_size
        sample_probs = self.get_probabilities(priority_scale)
        sample_indices = random.choices(range(self.mem_cntr), k=sample_size, weights=sample_probs[:self.mem_cntr])

        states = self.state_memory[sample_indices]
        actions = self.action_memory[sample_indices]
        rewards = self.reward_memory[sample_indices]
        states_ = self.new_state_memory[sample_indices]
        terminal = self.terminal_memory[sample_indices]

        # samples = np.array(self.buffer)[sample_indices]
        importance = self.get_importance(sample_probs[sample_indices])
        return states, actions, rewards, states_, terminal, importance, sample_indices

    def set_priorities(self, indices, errors, offset=0.1):
        for i,e in zip(indices, errors):
            error = abs(e) + offset
            clipped_error = np.minimum(error, 1.0)
            self.priorities[i] = clipped_error

    def save_data(self):
        np.save("data/states.npy", self.state_memory[:self.mem_cntr])
        np.save("data/states_.npy", self.new_state_memory[:self.mem_cntr])
        np.save("data/actions.npy", self.action_memory[:self.mem_cntr])
        np.save("data/priorities.npy", self.priorities[:self.mem_cntr])
        np.save("data/rewards.npy", self.reward_memory[:self.mem_cntr])
        np.save("data/terminal.npy", self.terminal_memory[:self.mem_cntr])
    
    def load_data(self):
        self.state_memory[:self.mem_cntr] = np.load("data/states.npy")
        self.new_state_memory[:self.mem_cntr] = np.load("data/states_.npy")
        self.action_memory[:self.mem_cntr] = np.load("data/actions.npy")
        self.reward_memory[:self.mem_cntr] = np.load("data/rewards.npy")
        self.terminal_memory[:self.mem_cntr] = np.load("data/terminal.npy")
        self.priorities[:self.mem_cntr] = np.load("data/priorities.npy")
