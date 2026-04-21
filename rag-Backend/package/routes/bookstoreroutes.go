package routes

import (
	"github.com/gin-gonic/gin"
	"github.com/keshav/bookstore/package/controllers"
)

func RegisterBookRoutes(router *gin.Engine) {
	router.POST("/books", controllers.CreateBook)
	router.GET("/books", controllers.GetBooks)
	router.GET("/books/:id", controllers.BookByID)
	router.PUT("/books/:id", controllers.Update)
	router.DELETE("/books/:id", controllers.Delete)
}
