#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jun  5 14:52:24 2019

@author: AIRocker
"""
import numpy as np
import cv2
import math
from scipy.ndimage.filters import gaussian_filter

def padRightDownCorner(img, stride, padValue):
    
    h = img.shape[0]
    w = img.shape[1]

    pad = 4 * [None]
    pad[0] = 0 # up
    pad[1] = 0 # left
    pad[2] = 0 if (h % stride == 0) else stride - (h % stride) # down
    pad[3] = 0 if (w % stride == 0) else stride - (w % stride) # right

    img_padded = np.pad(img, ((pad[0], pad[2]), (pad[1], pad[3]), (0, 0)), 'constant', constant_values=padValue) 

    return img_padded, pad

def peaks(heatmap, threshold): 
    
    thre1 = threshold # heatmap peak identifier threshold    
    all_peaks = []
    peak_counter = 0    
    for part in range(heatmap.shape[2]-1):
        map_ori = heatmap[:, :, part]
        one_heatmap = gaussian_filter(map_ori, sigma=3) # smooth the data
        map_left = np.zeros(one_heatmap.shape)
        map_left[1:, :] = one_heatmap[:-1, :]
        map_right = np.zeros(one_heatmap.shape)
        map_right[:-1, :] = one_heatmap[1:, :]
        map_up = np.zeros(one_heatmap.shape)
        map_up[:, 1:] = one_heatmap[:, :-1]
        map_down = np.zeros(one_heatmap.shape)
        map_down[:, :-1] = one_heatmap[:, 1:]
    
        peaks_binary = np.logical_and.reduce(
            (one_heatmap >= map_left, one_heatmap >= map_right, one_heatmap >= map_up, one_heatmap >= map_down, one_heatmap > thre1))
        # find the peak of surrounding with window size = 1 and above threshold
        peaks = list(zip(np.nonzero(peaks_binary)[1], np.nonzero(peaks_binary)[0]))  # note reverse
        peaks_with_score = [x + (map_ori[x[1], x[0]],) for x in peaks]
        peak_id = range(peak_counter, peak_counter + len(peaks))
        peaks_with_score_and_id = [peaks_with_score[i] + (peak_id[i],) for i in range(len(peak_id))]
        all_peaks.append(peaks_with_score_and_id)
        peak_counter += len(peaks)
        
    return all_peaks

def connection(all_peaks, paf, image):

    limbSeq = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], \
               [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], \
               [1, 16], [16, 18], [3, 17], [6, 18]]
    # the middle joints heatmap correpondence
    mapIdx = [[31, 32], [39, 40], [33, 34], [35, 36], [41, 42], [43, 44], [19, 20], [21, 22], \
              [23, 24], [25, 26], [27, 28], [29, 30], [47, 48], [49, 50], [53, 54], [51, 52], \
              [55, 56], [37, 38], [45, 46]]
    thre2 = 0.1 # connection and paf score threshold 
    connection_all = []
    special_k = []
    mid_num = 10
    for k in range(len(mapIdx)):
        score_mid = paf[:, :, [x - 19 for x in mapIdx[k]]]
        candA = all_peaks[limbSeq[k][0] - 1] # all detections of corresponding parts
        candB = all_peaks[limbSeq[k][1] - 1]
        nA = len(candA)
        nB = len(candB)
        indexA, indexB = limbSeq[k]  # part index
        if (nA != 0 and nB != 0):
            connection_candidate = []
            for i in range(nA):
                for j in range(nB):
                     vec = np.subtract(candB[j][:2], candA[i][:2]) # vec = [(x2-x1), (y2-y1)]
                     norm = math.sqrt(vec[0] * vec[0] + vec[1] * vec[1])
                     vec = np.divide(vec, norm) # unit vector for each candidate connection 
                     # startend is list that containing 10 linspaced cooridnates between the line of candA and candB
                     startend = list(zip(np.linspace(candA[i][0], candB[j][0], num=mid_num), \
                                                np.linspace(candA[i][1], candB[j][1], num=mid_num)))
                     # find out the vec(x,y) values from the startend cooridnates
                     vec_x = np.array([score_mid[int(round(startend[I][1])), int(round(startend[I][0])), 0] \
                                      for I in range(len(startend))])
                     vec_y = np.array([score_mid[int(round(startend[I][1])), int(round(startend[I][0])), 1] \
                                      for I in range(len(startend))])
                     # vector mulitpy between paf and candidate connection: array.shape = (10,)
                     score_midpts = np.multiply(vec_x, vec[0]) + np.multiply(vec_y, vec[1]) 
                     # calucate the average score + bonus if connection norm is lower than half test image height
                     score_with_dist_prior = sum(score_midpts) / len(score_midpts) + min(
                                0.5 * image.shape[0] / (norm+1e-16) - 1, 0)
                     # criterion1: if > 8 / 10 score_midpts is higher than 0.05
                     # criterion2: total score > 0
                     criterion1 = len(np.nonzero(score_midpts > thre2)[0]) > 0.8 * len(score_midpts)
                     criterion2 = score_with_dist_prior > 0
                     # record ith detection of indexA part and jth detection of indexB part with score 
                     if criterion1 and criterion2:
                         connection_candidate.append(
                                    [i, j, score_with_dist_prior, score_with_dist_prior + candA[i][2] + candB[j][2]])
            # sort based on the score_with_dist_prior             
            connection_candidate = sorted(connection_candidate, key=lambda x: x[2], reverse=True)
            connection = np.zeros((0, 5))
            for c in range(len(connection_candidate)):
                i, j, s = connection_candidate[c][0:3]
                if (i not in connection[:, 3] and j not in connection[:, 4]):
                    connection = np.vstack([connection, [candA[i][3], candB[j][3], s, i, j]])
                    if (len(connection) >= min(nA, nB)):
                        break
            # record all connectin info as peak id of part indexA, peak id of part indexB, total score, ith, jth
            connection_all.append(connection)
            
        else:
            # if nA or nB is empty record that connection case 
            special_k.append(k)
            connection_all.append([])
    
    return connection_all, special_k

def merge(all_peaks, connection_all, special_k):
    
    limbSeq = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], \
           [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], \
           [1, 16], [16, 18], [3, 17], [6, 18]]
    
    mapIdx = [[31, 32], [39, 40], [33, 34], [35, 36], [41, 42], [43, 44], [19, 20], [21, 22], \
              [23, 24], [25, 26], [27, 28], [29, 30], [47, 48], [49, 50], [53, 54], [51, 52], \
              [55, 56], [37, 38], [45, 46]]
    
    subset = -1 * np.ones((0, 20))
    # build up numpy array for peaks: x, y, score, id
    candidate = np.array([item for sublist in all_peaks for item in sublist])
    
    for k in range(len(mapIdx)):
        if k not in special_k:
            partAs = connection_all[k][:, 0]
            partBs = connection_all[k][:, 1]
            indexA, indexB = np.array(limbSeq[k]) - 1
    
            for i in range(len(connection_all[k])):  # = 1:size(temp,1)
                found = 0
                subset_idx = [-1, -1]
                for j in range(len(subset)):  # 1:size(subset,1):
                    if subset[j][indexA] == partAs[i] or subset[j][indexB] == partBs[i]:
                        subset_idx[found] = j
                        found += 1
    
                if found == 1:
                    j = subset_idx[0]
                    if subset[j][indexB] != partBs[i]:
                        subset[j][indexB] = partBs[i]
                        subset[j][-1] += 1
                        subset[j][-2] += candidate[partBs[i].astype(int), 2] + connection_all[k][i][2]
                elif found == 2:  # if found 2 and disjoint, merge them
                    j1, j2 = subset_idx
                    membership = ((subset[j1] >= 0).astype(int) + (subset[j2] >= 0).astype(int))[:-2]
                    if len(np.nonzero(membership == 2)[0]) == 0:  # merge
                        subset[j1][:-2] += (subset[j2][:-2] + 1)
                        subset[j1][-2:] += subset[j2][-2:]
                        subset[j1][-2] += connection_all[k][i][2]
                        subset = np.delete(subset, j2, 0)
                    else:  # as like found == 1
                        subset[j1][indexB] = partBs[i]
                        subset[j1][-1] += 1
                        subset[j1][-2] += candidate[partBs[i].astype(int), 2] + connection_all[k][i][2]
    
                # if find no partA in the subset, create a new subset
                elif not found and k < 17:
                    row = -1 * np.ones(20)
                    row[indexA] = partAs[i]
                    row[indexB] = partBs[i]
                    row[-1] = 2
                    row[-2] = sum(candidate[connection_all[k][i, :2].astype(int), 2]) + connection_all[k][i][2]
                    subset = np.vstack([subset, row])
    # delete some rows of subset which has few parts occur
    deleteIdx = []
    for i in range(len(subset)):
        if subset[i][-1] < 4 or subset[i][-2] / subset[i][-1] < 0.4:
            deleteIdx.append(i)
    # subset: n*20 array, 0-17 is the index in candidate, 18 is the total score, 19 is the total parts, n is the number of person 
    subset = np.delete(subset, deleteIdx, axis=0)
    
    return candidate, subset

def draw_bodypose(canvas, candidate, subset, scale=1):
    stickwidth = 2
    dotwidth = 2
    limbSeq = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], \
               [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17], \
               [1, 16], [16, 18], [3, 17], [6, 18]]

    colors = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0], \
              [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], \
              [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]
    for i in range(18):
        for n in range(len(subset)):
            index = int(subset[n][i])
            if index == -1:
                continue
            x, y = candidate[index][0:2]
            cv2.circle(canvas, (int(x/scale), int(y/scale)), int(dotwidth), colors[i], thickness=-1)
    for i in range(17):
        for n in range(len(subset)):
            index = subset[n][np.array(limbSeq[i]) - 1]
            if -1 in index:
                continue
            cur_canvas = canvas.copy()
            Y = candidate[index.astype(int), 0]/scale
            X = candidate[index.astype(int), 1]/scale
            mX = np.mean(X)
            mY = np.mean(Y)
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            polygon = cv2.ellipse2Poly((int(mY), int(mX)), (int(length / 2), int(stickwidth)), int(angle), 0, 360, 1)
            cv2.fillConvexPoly(cur_canvas, polygon, colors[i])
            canvas = cv2.addWeighted(canvas, 0.4, cur_canvas, 0.6, 0)
    return canvas

def draw_part(canvas, all_peaks, ID, scale=1):
    dotwidth = 8
    for i in range(len(ID)):
        for j in range(len(all_peaks[ID[i]])):
            cv2.circle(canvas, (int(all_peaks[ID[i]][j][0]/scale), int(all_peaks[ID[i]][j][1]/scale)), int(dotwidth), (0,0,255), thickness=-1)
        
    return canvas
