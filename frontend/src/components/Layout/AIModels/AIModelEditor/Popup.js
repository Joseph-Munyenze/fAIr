import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  CircularProgress,
} from "@mui/material";
import FileStructure from "./FileStructure";

import axios from "../../../../axios";
import FilesTree from "./FilesTree";
import LoadingButton from "@mui/lab/LoadingButton/LoadingButton";

const Popup = ({ open, handleClose, row }) => {
  const [error, setError] = useState(null);
  const [traceback, setTraceback] = useState(null);
  const [imageUrl, setImageUrl] = useState(null);
  const [trainingWorkspaceURL, settrainingWorkspaceURL] = useState(null);

  const [loading, setLoading] = useState(false);
  const [fileStructure, setFileStructure] = useState(null);
  const [dirHistory, setDirHistory] = useState([]);

  const getFileStructure = async (currentPath = "") => {
    try {
      const res = await axios.get(
        `/workspace/${trainingWorkspaceURL}${currentPath}`
      );
      if (res.error) {
        console.error(res.error);
      } else {
        setFileStructure(res.data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDirClick = (newPath) => {
    setDirHistory([...dirHistory, newPath]);
    getFileStructure(newPath);
  };

  const handleGoBack = () => {
    const newHistory = [...dirHistory];
    newHistory.pop();
    setDirHistory(newHistory);

    if (newHistory.length > 0) {
      getFileStructure(newHistory[newHistory.length - 1]);
    } else {
      getFileStructure();
    }
  };
  const getTrainingStatus = async (taskId) => {
    try {
      const res = await axios.get(`/training/status/${taskId}`);

      if (res.error) {
        setError(res.error.response.statusText);
        setTraceback(null);
      } else {
        setError(null);
        setTraceback(res.data.traceback);
      }
    } catch (e) {
      setError(e);
      setTraceback(null);
    }
  };

  const getDatasetId = async (modelId) => {
    try {
      const res = await axios.get(`/model/${modelId}`);

      if (res.error) {
        console.error(res.error);
      } else {
        setImageUrl(
          `${axios.defaults.baseURL}/workspace/download/dataset_${res.data.dataset}/output/training_${row.id}/graphs/training_validation_sparse_categorical_accuracy.png`
        );
        settrainingWorkspaceURL(
          `dataset_${res.data.dataset}/output/training_${row.id}/`
        );
      }
    } catch (e) {
      console.error(e);
    }
  };

  const renderTraceback = () => {
    if (!traceback) {
      return null;
    }

    return traceback.split("\n").map((line, index) => (
      <div key={index} style={{ display: "flex" }}>
        <span style={{ color: "gray", marginRight: "1em" }}>{index + 1}.</span>
        <span style={{ whiteSpace: "nowrap" }}>{line}</span>
      </div>
    ));
  };

  useEffect(() => {
    setLoading(true);
    if (row.status === "FAILED" || row.status === "RUNNING") {
      // Call getTrainingStatus every 3 seconds
      const intervalId = setInterval(() => {
        getTrainingStatus(row.task_id);
      }, 3000);

      getTrainingStatus(row.task_id).finally(() => setLoading(false));

      return () => clearInterval(intervalId);
    } else if (row.status === "FINISHED") {
      getDatasetId(row.model).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [row.status, row.task_id, row.model]);

  return (
    <Dialog open={open} onClose={handleClose}>
      <DialogTitle>
        Training {row.id} {row.description}
      </DialogTitle>
      <DialogContent>
        <p>
          <b>Epochs / Batch Size:</b> {row.epochs}/{row.batch_size}
        </p>
        <p>
          <b>Source Image (TMS): </b>
          {row.source_imagery}
        </p>

        <p>
          <b>Task Id:</b> {row.task_id}
        </p>
        <p>
          <b>Zoom Level:</b>{" "}
          {typeof row.zoom_level === "string"
            ? row.zoom_level
                .split(",")
                .reduce((acc, cur, i) => (i % 2 ? acc + ", " + cur : acc + cur))
            : row.zoom_level.toString()}
        </p>
        <p>
          <b>Accuracy:</b> {row.accuracy && row.accuracy.toFixed(2)} %
        </p>
        <p>
          <b>Status:</b> {row.status}
        </p>
        {/* <p>
          <b>Freeze Layers:</b> {row.freeze_layers}
        </p> */}
        {/* <div style={{ display: "flex", justifyContent: "space-between" }}>
          <LoadingButton
            onClick={() => getFileStructure()}
            style={{ color: "white", fontSize: "0.875rem" }}
          >
            Training Files
          </LoadingButton>
          {row.status === "FINISHED" && (
            <Button
              onClick={handleGoBack}
              disabled={dirHistory.length === 0}
              style={{ color: "white", fontSize: "0.875rem" }}
            >
              Go Back
            </Button>
          )}
        </div> */}
        {(row.status === "FAILED" || row.status === "RUNNING") && (
          <>
            {loading ? (
              <div style={{ display: "flex", justifyContent: "center" }}>
                <CircularProgress />
              </div>
            ) : (
              traceback && (
                <div
                  style={{
                    backgroundColor: "black",
                    color: "white",
                    padding: "10px",
                    fontSize: "12px",
                    whiteSpace: "pre-wrap",
                    fontFamily: "monospace",
                    overflow: "auto",
                  }}
                >
                  {renderTraceback()}
                </div>
              )
            )}
          </>
        )}
        {row.status === "FINISHED" && (
          <>
            {trainingWorkspaceURL && (
              <>
                {/* <FileStructure
                  name={`training_${row.id}`}
                  content={fileStructure}
                  path={
                    dirHistory.length > 0
                      ? dirHistory[dirHistory.length - 1]
                      : ""
                  }
                  isFile={false}
                  downloadUrl={`${axios.defaults.baseURL}/workspace/download/${trainingWorkspaceURL}`}
                  onDirClick={handleDirClick}
                /> */}
                <FilesTree
                  trainingId={row.id}
                  downloadUrl={`${axios.defaults.baseURL}/workspace/download/${trainingWorkspaceURL}`}
                  trainingWorkspaceURL={trainingWorkspaceURL}
                ></FilesTree>
              </>
            )}
            {loading ? (
              <div style={{ display: "flex", justifyContent: "center" }}>
                <CircularProgress />
              </div>
            ) : (
              imageUrl && (
                <div style={{ display: "flex", justifyContent: "center" }}>
                  <img
                    src={imageUrl}
                    alt="training graph"
                    style={{ width: "98%" }}
                  />
                </div>
              )
            )}
          </>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={handleClose} style={{ color: "white" }}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default Popup;
